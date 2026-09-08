# Soul Care Platform

A HIPAA-ready SaaS platform for Christian mental health coaches — smart intake with clinical risk routing, a dual-sided referral marketplace, church benevolence billing, scripture automation, scheduling, and a coaching CRM.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design (stack, DB schema, API routing, cloud infra) and [`docs/SECURITY_GRC_BLUEPRINT.md`](docs/SECURITY_GRC_BLUEPRINT.md) for the control mapping to NIST 800-53 / SOC 2 / ISO 27001.

**Status:** early MVP scaffold. Implemented so far: Smart Intake & Risk Assessment (the "Recognize" module, including the Safe-T/ACT hard-stop routing and substance-abuse referral logic), Auth/RBAC with JWT + refresh-token rotation, and the provider-vetting endpoint demonstrating role-based access control end to end. Every module below has been run and tested against a live Postgres + Redis, not just written.

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
