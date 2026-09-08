# System Architecture — Christian Mental Health Coaching Platform (MVP)

Working name used throughout this doc: **"Soul Care Platform"** (SCP) — rename freely.

## 1. Stack Overview

**Frontend:** React 18 + TypeScript, Vite, TanStack Query (server state), React Hook Form + Zod (form + schema validation shared conceptually with backend Pydantic models), Tailwind, deployed as static assets behind a CDN.

**Backend:** Python 3.12, FastAPI (chosen over Django for this MVP: async-first, native Pydantic validation that mirrors HIPAA data-minimization needs at the schema layer, OpenAPI docs generated for free, easier to run as small independently-scalable services later). Uvicorn/Gunicorn workers behind an ASGI-aware load balancer.

**Data layer:**
- PostgreSQL 15+ (primary system of record) — chosen for row-level security (RLS) support, which is used as a second enforcement layer under application-level access control for PHI isolation between coaches/churches/providers.
- Redis — session cache, rate limiting, short-lived job queue backing (Celery/RQ) for scripture delivery and notification dispatch.
- S3-compatible object storage (private bucket, SSE-KMS) — signed documents (ROI consent PDFs), uploaded intake attachments.
- Separate **encryption-at-rest key hierarchy** via a managed KMS (AWS KMS / GCP KMS) — envelope encryption for PHI columns (see field-level notes in §3).

**Async workers:** Celery (or RQ) + Redis broker for: risk-event notifications (SMS/email/pager to on-call clinical partner), scripture delivery, invoice generation, ROI expiration checks.

**Cloud infrastructure (MVP-appropriate, HIPAA-eligible services only):**
- AWS as reference cloud (GCP equally viable — both offer BAAs): VPC with private subnets for DB/workers, public subnet only for the ALB.
- ECS Fargate (or GKE Autopilot) for API and worker containers — no persistent SSH surface, reduces audit scope vs. raw EC2/VMs.
- RDS PostgreSQL Multi-AZ, encrypted, automated backups + point-in-time recovery, in a private subnet only.
- ElastiCache Redis, private subnet.
- S3 with bucket policies denying public access, versioning + object lock for consent documents (tamper-evidence).
- CloudFront + WAF in front of the React static bundle and the API (rate limiting, geo rules if needed, OWASP managed rule set).
- Secrets Manager / Parameter Store for all credentials — never in env files checked into source.
- CloudTrail + centralized logging (see audit design, §5) shipped to a log sink with restricted write-once access (e.g., S3 Object Lock or a SIEM like Wazuh/Elastic).
- All PHI-touching components sit behind a signed BAA with the cloud provider — this is a hard prerequisite, not an implementation detail, before any real client data enters the system.

**Environments:** dev / staging / prod, fully isolated accounts or at minimum isolated VPCs — no PHI in dev/staging (synthetic data only).

## 2. High-Level Component Diagram (text)

```
                         ┌─────────────────────────┐
                         │        CloudFront        │
                         │      + WAF (edge)        │
                         └────────────┬─────────────┘
                                      │
                 ┌────────────────────┼─────────────────────┐
                 │                    │                      │
        ┌────────▼────────┐  ┌────────▼─────────┐   ┌────────▼────────┐
        │ React SPA (S3)   │  │  ALB (TLS 1.2+)  │   │  Stripe Webhooks │
        │ static assets    │  │                   │   │  (signed, verified)
        └──────────────────┘  └────────┬──────────┘   └────────┬─────────┘
                                        │                        │
                              ┌─────────▼────────────────────────▼─────────┐
                              │        FastAPI app (ECS Fargate)           │
                              │  ┌────────────┬────────────┬────────────┐ │
                              │  │ Auth/RBAC  │  Intake &   │  Referral  │ │
                              │  │ (JWT+OIDC) │  Risk Engine│  Marketplace│ │
                              │  ├────────────┼────────────┼────────────┤ │
                              │  │ Consent/ROI│  Billing/   │  Scripture │ │
                              │  │ Service    │  Sponsorship│  Automation│ │
                              │  ├────────────┼────────────┼────────────┤ │
                              │  │ Scheduling │  Coaching   │  Audit Log │ │
                              │  │ / Prayer   │  CRM        │  Middleware│ │
                              │  └────────────┴────────────┴────────────┘ │
                              └─────────┬───────────────┬──────────────────┘
                                        │               │
                         ┌──────────────▼───┐   ┌───────▼────────────┐
                         │ Celery Workers    │   │  Redis (cache,     │
                         │ (notifications,   │   │  session, broker)  │
                         │ scripture, invoices)│  └─────────────────────┘
                         └──────────────┬────┘
                                        │
                         ┌──────────────▼─────────────┐
                         │  PostgreSQL (RLS enabled)   │
                         │  + S3 (consent docs, KMS)   │
                         └─────────────────────────────┘
```

## 3. Database Schema (core tables + relationships)

Notation: PK = primary key, FK = foreign key, 🔒 = field-level encrypted (application-layer envelope encryption on top of disk encryption — for data that must remain confidential even from a DB-level breach or insider with raw SQL access).

```
users
  id (PK, uuid)
  email 🔒
  hashed_password
  role            -- enum: client, coach, provider, church_admin, platform_admin
  mfa_enabled
  mfa_secret 🔒
  created_at, last_login_at

clients
  id (PK, uuid)
  user_id (FK -> users.id, unique)
  coach_id (FK -> coaches.id, nullable)
  church_sponsor_id (FK -> churches.id, nullable)
  date_of_birth 🔒
  emergency_contact 🔒
  created_at

coaches
  id (PK, uuid)
  user_id (FK -> users.id, unique)
  bio, certifications (JSONB)
  church_affiliation (FK -> churches.id, nullable)
  active (bool)

clinical_providers
  id (PK, uuid)
  user_id (FK -> users.id, unique)
  provider_type       -- enum: psychiatrist, licensed_counselor, addiction_specialist
  license_number 🔒
  license_state
  npi_number 🔒
  malpractice_verified (bool)
  vetting_status       -- enum: pending, in_review, approved, rejected, suspended
  accepting_referrals (bool)
  onboarded_at

churches
  id (PK, uuid)
  name
  tax_id 🔒
  primary_contact_user_id (FK -> users.id)
  billing_email
  created_at

intake_assessments
  id (PK, uuid)
  client_id (FK -> clients.id)
  submitted_at
  status                -- enum: draft, submitted, triaged, closed
  distress_level (int)  -- validated self-report scale
  phq9_score (int, nullable)   🔒
  gad7_score (int, nullable)   🔒
  protective_factors (JSONB)
  presenting_concerns (JSONB)  -- tags used by scripture engine, e.g. ["anxiety","grief"]
  raw_responses 🔒 (JSONB, encrypted blob of full intake answers)

risk_events
  id (PK, uuid)
  intake_assessment_id (FK -> intake_assessments.id)
  risk_type          -- enum: suicidal_ideation, substance_abuse, other_acute
  severity            -- enum: low, moderate, high, imminent
  protocol_triggered   -- enum: safe_t, act_model, addiction_referral, none
  triggered_at
  acknowledged_by (FK -> users.id, nullable)
  acknowledged_at
  resolution_notes 🔒

referrals
  id (PK, uuid)
  client_id (FK -> clients.id)
  provider_id (FK -> clinical_providers.id)
  risk_event_id (FK -> risk_events.id, nullable)  -- set when referral is crisis-triggered
  referral_type        -- enum: standard, urgent, emergency
  status               -- enum: pending, accepted, declined, completed, expired
  consent_id (FK -> roi_consents.id)
  created_at, responded_at

roi_consents
  id (PK, uuid)
  client_id (FK -> clients.id)
  discloses_to_provider_id (FK -> clinical_providers.id, nullable)
  discloses_to_church_id (FK -> churches.id, nullable)
  scope (JSONB)          -- exactly what may be shared (e.g., billing-only vs. clinical summary)
  signed_at
  signature_hash 🔒       -- hash of e-signature artifact stored in S3
  document_s3_key
  expires_at
  revoked_at

sponsorships
  id (PK, uuid)
  church_id (FK -> churches.id)
  client_id (FK -> clients.id)
  sponsor_type          -- enum: full, partial, per_session
  sessions_covered (int)
  amount_covered_cents   -- NOT tied to clinical detail
  start_date, end_date
  status

invoices
  id (PK, uuid)
  sponsorship_id (FK -> sponsorships.id, nullable)
  church_id (FK -> churches.id, nullable)
  client_id (FK -> clients.id, nullable)
  line_items (JSONB)     -- session dates/counts/amounts ONLY — no diagnosis, no notes
  stripe_payment_intent_id
  amount_cents, status, issued_at

sessions
  id (PK, uuid)
  client_id (FK -> clients.id)
  coach_id (FK -> coaches.id, nullable)
  provider_id (FK -> clinical_providers.id, nullable)
  session_type          -- enum: coaching, prayer, clinical
  scheduled_at, status
  -- notes reached via session_notes.session_id (reverse lookup only —
  -- no forward FK here, which would create a circular dependency with
  -- session_notes and break migration table-creation order)

session_notes
  id (PK, uuid)
  session_id (FK -> sessions.id)
  note_type              -- enum: spiritual_action_plan, progress, clinical
  encrypted_content 🔒
  created_by (FK -> users.id)
  created_at
  -- access control: note_type=clinical readable only by provider role + client; never by coach/church

prayer_requests
  id (PK, uuid)
  client_id (FK -> clients.id)
  request_text 🔒
  urgency               -- enum: routine, urgent, immediate
  assigned_to (FK -> users.id, nullable)
  status
  created_at

scripture_tags
  id (PK, serial)
  name (unique)          -- anxiety, grief, marital_conflict, addiction_recovery, ...

scripture_content
  id (PK, uuid)
  tag_id (FK -> scripture_tags.id)
  reference, verse_text, reflection_text, translation

scripture_deliveries
  id (PK, uuid)
  client_id (FK -> clients.id)
  scripture_content_id (FK -> scripture_content.id)
  channel               -- enum: dashboard, email, sms
  triggered_by_intake_id (FK -> intake_assessments.id, nullable)
  delivered_at

audit_logs   -- append-only, no UPDATE/DELETE grants at the DB role level
  id (PK, bigserial)
  actor_user_id (FK -> users.id, nullable)
  action                 -- e.g., "intake.submit", "note.read", "referral.create"
  resource_type, resource_id
  phi_accessed (bool)
  ip_address, user_agent
  occurred_at
```

**Key relationship notes:**
- `clients` is the hub PHI table; every clinical/behavioral table hangs off `client_id`.
- `churches` never link directly to `intake_assessments`, `risk_events`, or `session_notes` — only to `sponsorships`/`invoices`, which is the structural enforcement of "billing without clinical visibility."
- `roi_consents` is a hard dependency (FK, not just app logic) of `referrals` — a referral cannot be created without a consent row, enforced at the service layer and reinforced with a DB check constraint / trigger.
- `risk_events` is append-only and immutable once written (no client-facing edit path) to preserve a defensible clinical/legal trail.

## 4. API Routing (FastAPI, versioned under `/api/v1`)

```
/auth
  POST   /auth/register
  POST   /auth/login
  POST   /auth/mfa/verify
  POST   /auth/refresh
  POST   /auth/logout

/intake
  POST   /intake                      -- create draft assessment
  PATCH  /intake/{id}                 -- save progress
  POST   /intake/{id}/submit          -- triggers risk_engine + scripture_engine (see §6)
  GET    /intake/{id}                 -- role-scoped read

/referrals
  GET    /referrals?client_id=
  POST   /referrals                   -- standard (non-crisis) referral
  PATCH  /referrals/{id}/respond      -- provider accepts/declines

/providers
  POST   /providers/onboard
  GET    /providers/{id}/vetting-status
  PATCH  /providers/{id}/vetting      -- admin-only vetting decision

/consents
  POST   /consents/roi
  GET    /consents/roi/{id}
  POST   /consents/roi/{id}/revoke

/church
  POST   /church/sponsorships
  GET    /church/sponsorships/{id}
  GET    /church/invoices            -- billing detail only, no clinical join

/billing
  POST   /billing/invoices
  POST   /billing/stripe/webhook

/scripture
  GET    /scripture/tags
  GET    /scripture/deliveries?client_id=

/scheduling
  POST   /scheduling/sessions
  GET    /scheduling/sessions?client_id=
  POST   /scheduling/prayer-requests

/crm
  GET    /crm/clients/{id}/summary    -- coach view, excludes clinical note_type
  POST   /crm/clients/{id}/notes
```

Every route is wrapped by:
1. **AuthN middleware** (JWT validated against short-lived access token + refresh rotation).
2. **AuthZ dependency** (role + row-level ownership check — e.g., a coach can only read clients where `clients.coach_id == current_user.coach_id`).
3. **Audit middleware** that writes an `audit_logs` row on every read/write touching a PHI-bearing table, tagging `phi_accessed=True` automatically based on a table allowlist.

## 5. Audit & Logging Design

- Application-level audit log (`audit_logs` table, described above) is the source of truth for "who touched what PHI, when" — required by both NIST 800-53 (AU family) and SOC 2 (CC7).
- Infrastructure-level logs (ALB access logs, CloudTrail, RDS logs) ship to a separate, write-restricted log sink for correlation and intrusion detection, not for clinical audit purposes.
- Audit log table itself is append-only at the database role level (application's DB user has INSERT but not UPDATE/DELETE on `audit_logs`).

## 6. Request Flow — Intake Submission (ties §3 schema to the code deliverable)

1. Client submits intake via React form → `POST /intake/{id}/submit`.
2. FastAPI validates payload against Pydantic schema (`IntakeSubmission`).
3. `risk_engine.evaluate(intake)` runs deterministic rule checks (not an LLM judgment call for the hard-stop paths) against structured fields (e.g., a validated suicide-risk screener item, a substance-use screener item).
4. If a hard-stop condition fires: a `risk_events` row is written, a `referrals` row is created against an on-call/available provider of the correct type, and a notification job is enqueued (SMS/pager to clinical on-call) — all inside the same DB transaction as the intake update, so a referral is never silently dropped.
5. Regardless of risk outcome, `scripture_engine.dispatch(intake.presenting_concerns, client_id)` enqueues scripture delivery for the tags detected.
6. Response returns a routing decision to the frontend, which renders the appropriate UI (crisis resources / referral confirmation, or standard next-steps + scripture card).

## 7. MVP Build Sequence (suggested)

1. Auth + RBAC + audit middleware skeleton (nothing else matters without this foundation given the PHI in play).
2. Intake + risk engine (this document's code deliverable).
3. Provider onboarding + vetting workflow.
4. ROI consent + referral marketplace.
5. Scripture automation.
6. Scheduling/prayer routing.
7. Church sponsorship + billing (Stripe Connect for multi-party payouts is worth evaluating once provider payments are in scope).
8. Coaching CRM.
