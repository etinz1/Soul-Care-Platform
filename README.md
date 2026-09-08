# Soul Care Platform

A HIPAA-ready SaaS platform for Christian mental health coaches — smart intake with clinical risk routing, a dual-sided referral marketplace, church benevolence billing, scripture automation, scheduling, and a coaching CRM.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design (stack, DB schema, API routing, cloud infra) and [`docs/SECURITY_GRC_BLUEPRINT.md`](docs/SECURITY_GRC_BLUEPRINT.md) for the control mapping to NIST 800-53 / SOC 2 / ISO 27001.

**Status:** all 8 modules in ARCHITECTURE.md §7's suggested MVP build sequence are implemented: Auth/RBAC (JWT + refresh-token rotation), Smart Intake & Risk Assessment ("Recognize" — Safe-T/ACT hard-stop routing, substance-abuse referral logic), Scripture Automation, Provider Onboarding & Vetting, ROI Consent + Referral Marketplace ("Refer"), Scheduling & Prayer-Request Routing, Church Sponsorship & Billing (including a real HMAC-SHA256-verified Stripe webhook), and the Coaching CRM — plus a client self-service profile/onboarding flow and an intake-draft-creation endpoint that closed two real gaps in the original module handoffs. 72 backend tests pass against a live Postgres + Redis, GitHub Actions CI runs the backend suite and an Alembic migration round-trip on every push, and every backend module has also been exercised against the real dev server, not just the test suite.

The React frontend now covers the full client experience end to end: register, sign in (JWT stored client-side with automatic refresh-and-retry on 401), a dashboard showing profile/sessions/prayer requests, profile editing, and the Smart Intake form wired to real `POST /intake` + `POST /intake/{id}/submit` calls instead of hardcoded dev IDs. Coach/provider/admin screens aren't built yet — those roles can only be exercised via `/docs` or a direct API client for now. A second GitHub Actions workflow builds and tests the frontend (vitest + a production build) on every push. See "Important caveats" below for what's still missing before any of this touches real client data.

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

14 tests cover the risk-engine branch logic (every hard-stop and non-hard-stop path), scripture dispatch, and full HTTP integration tests for register/login/refresh/RBAC and the intake submission flow (including verifying a hard-stop intake creates a `risk_events` row, an emergency-exception `roi_consents` row, a `referrals` row, and the audit trail, all in one transaction).

## Repo layout

```
backend/
  app/
    models.py            # SQLAlchemy schema
    schemas.py            # Pydantic request/response models
    security.py            # password hashing + JWT issuance/validation
    auth.py                # FastAPI auth dependencies (get_current_user, require_role)
    redis_client.py        # refresh-token allowlist
    audit.py                # audit_logs writer
    services/
      risk_engine.py        # Safe-T/ACT hard-stop + substance-abuse routing logic
      scripture_engine.py    # presenting-concern -> scripture content + delivery dispatch
    api/v1/
      auth.py                # register/login/refresh/logout
      intake.py              # POST /intake/{id}/submit
      providers.py            # provider vetting (RBAC demo route)
  alembic/                    # migrations
  tests/                        # pytest suite
frontend/
  src/components/IntakeForm.jsx  # Smart Intake form
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
- There is no self-service endpoint yet for a registered client to complete their `Client` profile (assign a coach, set date of birth, etc.) or for a church to self-onboard — both are currently created directly (seed script / admin-only `POST /church`). A `PATCH /clients/me` (or similar) onboarding flow is the natural next piece of work before a real user could complete signup end to end.
