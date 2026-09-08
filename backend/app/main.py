from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.intake import router as intake_router
from app.api.v1.providers import router as providers_router

app = FastAPI(title="Soul Care Platform API", version="0.1.0")

app.include_router(auth_router, prefix="/api/v1")
app.include_router(intake_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
