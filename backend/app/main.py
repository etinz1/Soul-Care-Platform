from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.church import router as church_router
from app.api.v1.consents import router as consents_router
from app.api.v1.intake import router as intake_router
from app.api.v1.prayer_requests import router as prayer_requests_router
from app.api.v1.providers import router as providers_router
from app.api.v1.referrals import router as referrals_router
from app.api.v1.scheduling_sessions import router as scheduling_sessions_router

app = FastAPI(title="Soul Care Platform API", version="0.1.0")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(intake_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")
app.include_router(consents_router, prefix="/api/v1")
app.include_router(referrals_router, prefix="/api/v1")
app.include_router(scheduling_sessions_router, prefix="/api/v1")
app.include_router(prayer_requests_router, prefix="/api/v1")
app.include_router(church_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
