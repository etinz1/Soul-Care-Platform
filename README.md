# Soul Care Platform

A HIPAA-ready SaaS platform for Christian mental health coaches — smart intake with clinical risk routing, a dual-sided referral marketplace, church benevolence billing, scripture automation, scheduling, and a coaching CRM.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design (stack, DB schema, API routing, cloud infra) and [`docs/SECURITY_GRC_BLUEPRINT.md`](docs/SECURITY_GRC_BLUEPRINT.md) for the control mapping to NIST 800-53 / SOC 2 / ISO 27001.

**Status:** all 8 modules in ARCHITECTURE.md §7's suggested MVP build sequence are implemented: Auth/RBAC (JWT + refresh-token rotation), Smart Intake & Risk Assessment ("Recognize" — Safe-T/ACT hard-stop routing, substance-abuse referral logic), Scripture Automation (now with real delivery persistence, not just a synchronous response payload), Provider Onboarding & Vetting (including public self-onboarding), ROI Consent + Referral Marketplace ("Refer", including client-facing provider browsing), Scheduling & Prayer-Request Routing, Church Sponsorship & Billing (including a real HMAC-SHA256-verified Stripe webhook), and the Coaching CRM — plus a client self-service profile/onboarding flow, an intake-draft-creation endpoint, admin-only coach provisioning (`/coaches`), a church directory (`GET /church`) with a church-admin self-service lookup (`GET /church/me`), and a `GET /providers/me` self-service lookup that closed several real gaps left open by the original module handoffs. 96 backend tests pass against a live Postgres + Redis, GitHub Actions CI runs the backend suite and an Alembic migration round-trip on every push, and every backend module has also been exercised against the real dev server, not just the test suite.

The React frontend now covers all five roles with working dashboards. Clients get the full signup-to-care experience: register, sign in (JWT stored client-side with automatic refresh-and-retry on 401), a dashboard with profile/sessions/scripture cards delivered to them/a referral request flow (browse approved providers, sign ROI consent, request a referral)/prayer request submission, and the Smart Intake form wired to real `POST /intake` + `POST /intake/{id}/submit` calls. Coaches get a caseload roster with per-client summaries (presenting concerns, session/prayer counts, notes) and can schedule sessions and triage prayer requests. Providers see their own vetting status, respond to referrals, schedule clinical sessions against accepted referrals, and add session notes — and clinical providers can self-onboard from a public page (`/provider-onboarding`) rather than needing to be admin-provisioned. Church admins get a read-only dashboard showing their church record, sponsorships, and invoices. Platform admins get a single dashboard covering the provider vetting queue, coach and church provisioning, client-to-coach/church assignment, and invoice creation. A second GitHub Actions workflow builds and tests the frontend (vitest + a production build) on every push.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Redis
- **Frontend:** React 18, Vite, Tailwind
- **Infra (local dev):** Docker Compose

## Quick start (Docker Compose)

```bash
cp .env.example .env    # fill in JWT_SECRET_KEY at minimum
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173

Then, in a separate shell, run migrations and seed demo data:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

The seed script creates a demo client, an approved+accepting psychiatrist, an approved+accepting addiction specialist, and a platform admin (see `app/seed.py` for the demo password — dev/demo only, never reuse it anywhere real).

## Running without Docker

Requires local Postgres 15+ and Redis.

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://soul_care:soul_care_dev_password@localhost:5432/soul_care
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET_KEY=some-long-random-value
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
# Point at a dedicated test database — the suite drops/recreates its schema on every run.
export DATABASE_URL=postgresql+asyncpg://soul_care:soul_care_dev_password@localhost:5432/soul_care_test
export REDIS_URL=redis://localhost:6379/1
export JWT_SECRET_KEY=test-only-secret
pytest
```

96 tests cover the risk-engine branch logic (every hard-stop and non-hard-stop path), scripture dispatch and delivery persistence (including get-or-create dedup of `ScriptureContent` rows across repeated dispatches), and full HTTP integration tests across every module — register/login/refresh/RBAC, the intake submission flow (including verifying a hard-stop intake creates a `risk_events` row, an emergency-exception `roi_consents` row, a `referrals` row, and the audit trail, all in one transaction), provider vetting and self-onboarding, the client-facing provider directory, ROI consent + referrals (including ROI scope surfaced on referral responses), scheduling + prayer routing, church sponsorship + billing + the church-admin self-service lookup (including Stripe signature verification), the coaching CRM, and coach/client provisioning and assignment.

## Repo layout

```
backend/
  app/
    models.py               # SQLAlchemy schema
    schemas.py               # Pydantic request/response models
    security.py               # password hashing, JWT issuance/validation, Stripe webhook signature check
    auth.py                   # FastAPI auth dependencies (get_current_user, require_role)
    redis_client.py           # refresh-token allowlist
    audit.py                   # audit_logs writer
    services/
      risk_engine.py           # Safe-T/ACT hard-stop + substance-abuse routing logic
      scripture_engine.py       # presenting-concern -> scripture content + delivery dispatch (persists ScriptureDelivery rows)
    api/v1/
      auth.py                   # register/login/refresh/logout
      clients.py                 # client self-service profile + admin coach/church assignment
      coaches.py                 # admin-only coach provisioning + listing
      intake.py                  # draft creation, fetch, and submission
      providers.py                # provider self-onboarding, vetting queue, GET /providers/me, GET /providers/directory (client-facing)
      scripture.py                 # GET /scripture/deliveries (client-facing)
      consents.py                  # ROI consent create/view/revoke
      referrals.py                  # referral marketplace
      scheduling_sessions.py         # session scheduling + notes
      prayer_requests.py              # prayer request routing
      church.py                        # church directory, GET /church/me (church-admin self-service), sponsorships, invoice reads
      billing.py                        # invoice creation, Stripe webhook receiver
      crm.py                             # coach caseload roster, client summaries, CRM notes
  alembic/                                # migrations
  tests/                                    # pytest suite (96 tests)
frontend/
  src/
    api/client.js              # fetch wrapper (auth, refresh-and-retry, all API groups)
    context/AuthContext.jsx    # JWT session state
    components/
      IntakeForm.jsx            # Smart Intake form
      ProtectedRoute.jsx, NavBar.jsx
    pages/
      LoginPage.jsx, RegisterPage.jsx
      ProviderOnboardingPage.jsx  # public clinical-provider self-onboarding form
      DashboardPage.jsx          # role router
      ClientDashboardPage.jsx     # profile, sessions, scripture cards, referral requests, prayer requests
      CoachDashboardPage.jsx, ProviderDashboardPage.jsx, AdminDashboardPage.jsx, ChurchAdminDashboardPage.jsx
      IntakePage.jsx
docs/
  ARCHITECTURE.md
  SECURITY_GRC_BLUEPRINT.md
```

## Important caveats before this touches real client data

- The clinical thresholds in `risk_engine.py` are a software routing scaffold, not clinical judgment — a licensed clinical supervisor must review and sign off on the actual screener choice and thresholds.
- The emergency-consent pattern in `intake.py` (`_get_or_create_emergency_consent`) relies on HIPAA's emergency-treatment exception for hard-stop referrals; legal/compliance should review this before launch.
- Field-level encryption (the `PHI:encrypted` fields noted in `models.py`) is not yet wired to a KMS-backed `EncryptedType` — that's the next piece of the security blueprint to implement before any real PHI is stored.
- No BAAs are signed yet with any infrastructure or third-party vendor. Don't put real client data in this system until they are.
- The typed-signature ROI consent (`hash_typed_signature` in `security.py`) is a placeholder — replace with a real e-signature vendor (DocuSign/HelloSign) before collecting real consent documents.
- The Stripe integration only implements webhook *signature verification and reconciliation* (`billing.py`); nothing yet calls the Stripe API to actually create a PaymentIntent or Checkout Session — that's the other half of a real integration.
- Coach accounts are admin-provisioned only (`POST /coaches`), same posture as churches — there's still no coach-facing self-onboarding/vetting flow the way clinical providers now have one.
- The admin dashboard's invoice creator is a single-line-item form for the MVP; multi-line invoices already work against the API (`POST /billing/invoices` takes a `line_items` array) but the UI only builds one at a time.
