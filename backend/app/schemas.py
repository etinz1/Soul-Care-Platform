"""
Pydantic schemas for the Smart Intake & Risk Assessment module.

These are intentionally strict: the two screener fields that can trigger a
hard-stop clinical protocol (`c9_suicidal_ideation` and
`substance_use_severity`) are validated, bounded-range fields, not free text,
so the risk engine's routing logic (services/risk_engine.py) is deterministic
and testable rather than inferring risk from prose.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# --- Auth ---


class RegisterRequest(BaseModel):
    """
    Public self-registration is intentionally restricted to the `client`
    role. Coaches and platform admins are provisioned by an existing admin;
    clinical providers go through the vetting workflow in /providers/onboard
    rather than plain registration (see ARCHITECTURE.md §7).
    """

    email: EmailStr
    password: str = Field(..., min_length=12)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PresentingConcern(str, Enum):
    anxiety = "anxiety"
    depression = "depression"
    grief = "grief"
    marital_conflict = "marital_conflict"
    parenting = "parenting"
    addiction_recovery = "addiction_recovery"
    identity_purpose = "identity_purpose"
    financial_stress = "financial_stress"
    spiritual_dryness = "spiritual_dryness"
    trauma_history = "trauma_history"


class IntakeSubmission(BaseModel):
    """
    Payload for POST /intake/{id}/submit.

    c9_suicidal_ideation mirrors PHQ-9 item 9 ("thoughts that you would be
    better off dead, or of hurting yourself"), scored 0-3 per the validated
    instrument (0=not at all, 1=several days, 2=more than half the days,
    3=nearly every day). ANY score >= 1 is treated as a hard-stop trigger
    per the Safe-T model's guidance that item-9 endorsement always warrants
    direct follow-up, regardless of total PHQ-9 score.
    """

    client_id: UUID
    distress_level: int = Field(..., ge=0, le=10, description="Self-reported overall distress, 0-10")
    phq9_score: Optional[int] = Field(None, ge=0, le=27)
    gad7_score: Optional[int] = Field(None, ge=0, le=21)
    c9_suicidal_ideation: int = Field(
        ..., ge=0, le=3, description="PHQ-9 item 9 score: thoughts of self-harm/death"
    )
    substance_use_severity: int = Field(
        ..., ge=0, le=4, description="Validated single-item substance-use screener (e.g., NIDA Quick Screen), 0-4"
    )
    protective_factors: list[str] = Field(default_factory=list)
    presenting_concerns: list[PresentingConcern] = Field(default_factory=list)
    raw_responses: dict = Field(default_factory=dict, description="Full structured intake answers")

    @field_validator("presenting_concerns")
    @classmethod
    def require_at_least_one_concern(cls, v):
        if not v:
            raise ValueError("At least one presenting concern must be selected.")
        return v


class RiskDecision(BaseModel):
    """Returned by the risk engine and surfaced to the frontend to drive routing UI."""

    risk_type: Optional[str] = None  # suicidal_ideation | substance_abuse | None
    severity: Optional[str] = None  # low | moderate | high | imminent
    protocol_triggered: str = "none"  # safe_t | act_model | addiction_referral | none
    is_hard_stop: bool = False
    referral_id: Optional[UUID] = None
    routed_provider_type: Optional[str] = None
    message: str


class ScriptureCard(BaseModel):
    reference: str
    verse_text: str
    reflection_text: Optional[str] = None
    translation: str = "ESV"


class IntakeSubmitResponse(BaseModel):
    intake_id: UUID
    status: str
    submitted_at: datetime
    risk_decision: RiskDecision
    scripture_cards: list[ScriptureCard] = Field(default_factory=list)
