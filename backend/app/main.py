import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.church import router as church_router
from app.api.v1.clients import router as clients_router
from app.api.v1.coaches import router as coaches_router
from app.api.v1.consents import router as consents_router
from app.api.v1.crm import router as crm_router
from app.api.v1.intake import router as intake_router
from app.api.v1.prayer_requests import router as prayer_requests_router
from app.api.v1.providers import router as providers_router
from app.api.v1.referrals import router as referrals_router
from app.api.v1.scheduling_sessions import router as scheduling_sessions_router
from app.api.v1.scripture import router as scripture_router

app = FastAPI(title="Soul Care Platform API", version="0.1.0")

# The React frontend (Vite dev server on :5173, or wherever it's deployed)
# calls this API from a different origin than the backend, so without CORS
# every browser request — not just cross-site ones — is blocked by the
# browser itself before it reaches any route. Auth is Bearer-token-in-header
# (see api/client.js), never cookies, so allow_credentials stays False; the
# allowed origin list is explicit rather than "*" so this doesn't quietly
# open up to every origin once a real domain replaces localhost.
_default_cors_origins = "http://localhost:5173,http://127.0.0.1:5173"
_cors_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_cors_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(intake_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")
app.include_router(consents_router, prefix="/api/v1")
app.include_router(referrals_router, prefix="/api/v1")
app.include_router(scheduling_sessions_router, prefix="/api/v1")
app.include_router(prayer_requests_router, prefix="/api/v1")
app.include_router(church_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")
app.include_router(coaches_router, prefix="/api/v1")
app.include_router(scripture_router, prefix="/api/v1")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
