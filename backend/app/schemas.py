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

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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


class IntakeCreateRequest(BaseModel):
    client_id: UUID


class IntakeDraftResponse(BaseModel):
    intake_id: UUID
    client_id: UUID
    status: str


class IntakeDetailResponse(BaseModel):
    """
    Role-scoped read (GET /intake/{id}). Deliberately narrower than the
    full IntakeAssessment row: no PHQ-9/GAD-7 scores and no raw_responses
    blob here, matching the same "don't over-expose clinical detail on a
    general read" posture as ClientSummaryResponse in the CRM module —
    those numeric scores are meant to inform the risk engine and a
    clinician, not to be casually re-fetched by the coach view this
    endpoint mostly serves.
    """

    intake_id: UUID
    client_id: UUID
    status: str
    submitted_at: Optional[datetime] = None
    distress_level: Optional[int] = None
    presenting_concerns: list[str] = Field(default_factory=list)
    protective_factors: list[str] = Field(default_factory=list)


# --- Provider onboarding ---


class ProviderOnboardRequest(BaseModel):
    """
    Public self-service onboarding for clinical providers. Unlike client
    /auth/register, this does NOT grant network membership on its own — it
    creates the account plus a `pending` ClinicalProvider row. A platform
    admin must review and approve (PATCH /providers/{id}/vetting) before the
    provider can receive referrals. See SECURITY_GRC_BLUEPRINT.md §4.
    """

    email: EmailStr
    password: str = Field(..., min_length=12)
    provider_type: str = Field(..., description="psychiatrist | licensed_counselor | addiction_specialist")
    license_number: str = Field(..., min_length=1)
    license_state: str = Field(..., min_length=2, max_length=2)
    npi_number: Optional[str] = None


class ProviderOnboardResponse(BaseModel):
    provider_id: UUID
    vetting_status: str
    accepting_referrals: bool
    tokens: TokenResponse


class ProviderSummary(BaseModel):
    provider_id: UUID
    provider_type: str
    license_state: str
    vetting_status: str
    accepting_referrals: bool


# --- ROI consent ---


class ConsentCreateRequest(BaseModel):
    """
    A lightweight typed e-signature for the MVP: the client types their full
    legal name as an attestation, which is hashed together with the scope
    and timestamp into `signature_hash`. This is a placeholder — a real
    e-signature vendor (e.g. HelloSign/DocuSign with an audit certificate)
    should replace it before real ROI documents are collected; see
    README.md's pre-launch caveats.
    """

    client_id: UUID
    discloses_to_provider_id: Optional[UUID] = None
    discloses_to_church_id: Optional[UUID] = None
    scope: dict = Field(default_factory=dict, description='e.g. {"clinical_summary": true}')
    typed_signature_name: str = Field(..., min_length=2)
    expires_in_days: int = Field(90, ge=1, le=365)

    @model_validator(mode="after")
    def exactly_one_disclosure_target(self):
        # field_validator alone would not fire here: pydantic v2 skips
        # per-field validation on defaulted (omitted) fields unless
        # validate_default=True, and both targets are optional-with-default.
        # A model validator always runs regardless of which fields were
        # actually supplied in the payload.
        if bool(self.discloses_to_church_id) == bool(self.discloses_to_provider_id):
            raise ValueError("Consent must disclose to exactly one of provider or church, not both or neither.")
        return self


class ConsentResponse(BaseModel):
    consent_id: UUID
    client_id: UUID
    discloses_to_provider_id: Optional[UUID] = None
    discloses_to_church_id: Optional[UUID] = None
    scope: dict
    signed_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


# --- Referrals ---


class ReferralCreateRequest(BaseModel):
    client_id: UUID
    provider_id: UUID
    consent_id: UUID
    referral_type: str = Field("standard", description="standard | urgent")


class ReferralResponse(BaseModel):
    referral_id: UUID
    client_id: UUID
    provider_id: UUID
    referral_type: str
    status: str
    created_at: datetime


class ReferralRespondRequest(BaseModel):
    status: str = Field(..., description="accepted | declined")

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in ("accepted", "declined"):
            raise ValueError("status must be 'accepted' or 'declined'")
        return v


# --- Scheduling: sessions ---


class SessionCreateRequest(BaseModel):
    client_id: UUID
    session_type: str = Field(..., description="coaching | prayer | clinical")
    scheduled_at: datetime

    @field_validator("session_type")
    @classmethod
    def valid_session_type(cls, v):
        if v not in ("coaching", "prayer", "clinical"):
            raise ValueError("session_type must be one of coaching, prayer, clinical")
        return v


class SessionResponse(BaseModel):
    session_id: UUID
    client_id: UUID
    coach_id: Optional[UUID] = None
    provider_id: Optional[UUID] = None
    session_type: str
    scheduled_at: datetime
    status: str


class SessionUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, description="scheduled | completed | cancelled | no_show")
    scheduled_at: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v is not None and v not in ("scheduled", "completed", "cancelled", "no_show"):
            raise ValueError("status must be one of scheduled, completed, cancelled, no_show")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.status is None and self.scheduled_at is None:
            raise ValueError("Provide at least one of status or scheduled_at.")
        return self


class SessionNoteCreateRequest(BaseModel):
    note_type: str = Field(..., description="spiritual_action_plan | progress | clinical")
    content: str = Field(..., min_length=1, description="Note body; stored in encrypted_content")

    @field_validator("note_type")
    @classmethod
    def valid_note_type(cls, v):
        if v not in ("spiritual_action_plan", "progress", "clinical"):
            raise ValueError("note_type must be one of spiritual_action_plan, progress, clinical")
        return v


class SessionNoteResponse(BaseModel):
    note_id: UUID
    session_id: UUID
    note_type: str
    content: str
    created_by: UUID
    created_at: datetime


# --- Scheduling: prayer requests ---


class PrayerRequestCreateRequest(BaseModel):
    client_id: UUID
    request_text: str = Field(..., min_length=1)
    urgency: str = Field("routine", description="routine | urgent | immediate")

    @field_validator("urgency")
    @classmethod
    def valid_urgency(cls, v):
        if v not in ("routine", "urgent", "immediate"):
            raise ValueError("urgency must be one of routine, urgent, immediate")
        return v


class PrayerRequestResponse(BaseModel):
    prayer_request_id: UUID
    client_id: UUID
    request_text: str
    urgency: str
    assigned_to: Optional[UUID] = None
    status: str
    created_at: datetime


class PrayerRequestUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, description="open | in_progress | closed")
    assigned_to: Optional[UUID] = Field(None, description="Admin-only reassignment")

    @field_validator("status")
    @classmethod
    def valid_prayer_status(cls, v):
        if v is not None and v not in ("open", "in_progress", "closed"):
            raise ValueError("status must be one of open, in_progress, closed")
        return v

    @model_validator(mode="after")
    def at_least_one_prayer_field(self):
        if self.status is None and self.assigned_to is None:
            raise ValueError("Provide at least one of status or assigned_to.")
        return self


# --- Church + sponsorship + billing ---


class ChurchCreateRequest(BaseModel):
    """Admin-only provisioning: churches are onboarded by platform staff, not self-service
    (there is no public /church/register — see ARCHITECTURE.md §4's API surface)."""

    name: str = Field(..., min_length=1)
    tax_id: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    primary_contact_user_id: Optional[UUID] = Field(
        None, description="Must reference an existing user with role=church_admin"
    )


class ChurchResponse(BaseModel):
    church_id: UUID
    name: str
    billing_email: Optional[str] = None
    primary_contact_user_id: Optional[UUID] = None
    created_at: datetime


class SponsorshipCreateRequest(BaseModel):
    """
    A church can only sponsor a client it has an ROI consent to be
    disclosed to (`consent_id`) — mirrors the referral module's
    consent-gating in api/v1/referrals.py, since a sponsorship reveals to
    the church that this client is receiving care.
    """

    client_id: UUID
    church_id: UUID
    consent_id: UUID
    sponsor_type: str = Field("full", description="full | partial | per_session")
    sessions_covered: int = Field(0, ge=0)
    amount_covered_cents: int = Field(0, ge=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @field_validator("sponsor_type")
    @classmethod
    def valid_sponsor_type(cls, v):
        if v not in ("full", "partial", "per_session"):
            raise ValueError("sponsor_type must be one of full, partial, per_session")
        return v


class SponsorshipResponse(BaseModel):
    sponsorship_id: UUID
    church_id: UUID
    client_id: UUID
    sponsor_type: str
    sessions_covered: int
    amount_covered_cents: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str


class SponsorshipUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, description="active | ended | suspended")
    end_date: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def valid_sponsorship_status(cls, v):
        if v is not None and v not in ("active", "ended", "suspended"):
            raise ValueError("status must be one of active, ended, suspended")
        return v

    @model_validator(mode="after")
    def at_least_one_sponsorship_field(self):
        if self.status is None and self.end_date is None:
            raise ValueError("Provide at least one of status or end_date.")
        return self


class InvoiceLineItem(BaseModel):
    """
    Deliberately narrow: session date/count/amount ONLY. There is no field
    here for a diagnosis, a note, or any other clinical detail — this is
    the structural half of "billing without clinical visibility"
    (ARCHITECTURE.md §3); the other half is that `churches` has no FK path
    to `intake_assessments`, `risk_events`, or `session_notes` at all.
    """

    session_id: Optional[UUID] = None
    session_date: Optional[datetime] = None
    description: str = Field(..., min_length=1)
    amount_cents: int = Field(..., ge=0)


class InvoiceCreateRequest(BaseModel):
    church_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    sponsorship_id: Optional[UUID] = None
    line_items: list[InvoiceLineItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def bills_someone(self):
        if self.church_id is None and self.client_id is None:
            raise ValueError("An invoice must be billed to a church, a client, or both.")
        return self


class InvoiceResponse(BaseModel):
    invoice_id: UUID
    sponsorship_id: Optional[UUID] = None
    church_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    line_items: list[dict]
    amount_cents: int
    status: str
    stripe_payment_intent_id: Optional[str] = None
    issued_at: datetime


# --- Client profile ---


class ClientProfileResponse(BaseModel):
    client_id: UUID
    user_id: UUID
    coach_id: Optional[UUID] = None
    church_sponsor_id: Optional[UUID] = None
    date_of_birth: Optional[str] = None
    emergency_contact: Optional[str] = None
    created_at: datetime


class ClientProfileUpdateRequest(BaseModel):
    """Self-service fields only — a client can fill in their own profile
    details, but cannot assign themselves a coach or a sponsoring church
    (see ClientAdminAssignRequest, which is admin-only)."""

    date_of_birth: Optional[str] = None
    emergency_contact: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_profile_field(self):
        if self.date_of_birth is None and self.emergency_contact is None:
            raise ValueError("Provide at least one of date_of_birth or emergency_contact.")
        return self


class ClientAdminAssignRequest(BaseModel):
    """Admin-only: assigning a coach or a sponsoring church is an
    operational decision, not something a client can grant themselves."""

    coach_id: Optional[UUID] = None
    church_sponsor_id: Optional[UUID] = None

    @model_validator(mode="after")
    def at_least_one_assignment_field(self):
        if self.coach_id is None and self.church_sponsor_id is None:
            raise ValueError("Provide at least one of coach_id or church_sponsor_id.")
        return self


# --- Coaching CRM ---


class ClientRosterEntry(BaseModel):
    client_id: UUID
    coach_id: Optional[UUID] = None
    church_sponsor_id: Optional[UUID] = None
    created_at: datetime


class CrmNoteCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class CrmNoteResponse(BaseModel):
    note_id: UUID
    client_id: UUID
    coach_id: Optional[UUID] = None
    content: str
    created_by: UUID
    created_at: datetime


class ClientSummaryResponse(BaseModel):
    """
    The coach's operational view of a client. Deliberately excludes
    note_type=clinical session notes, PHQ-9/GAD-7 scores, raw intake
    responses, and risk events entirely — those stay behind the
    provider/admin-only surfaces in api/v1/scheduling_sessions.py and
    api/v1/intake.py. See ARCHITECTURE.md §4's `/crm` comment: "coach view,
    excludes clinical note_type."
    """

    client_id: UUID
    coach_id: Optional[UUID] = None
    church_sponsor_id: Optional[UUID] = None
    created_at: datetime
    latest_intake_submitted_at: Optional[datetime] = None
    presenting_concerns: list[str] = Field(default_factory=list)
    protective_factors: list[str] = Field(default_factory=list)
    distress_level: Optional[int] = None
    upcoming_sessions_count: int = 0
    completed_sessions_count: int = 0
    open_prayer_requests_count: int = 0
    recent_session_notes: list[SessionNoteResponse] = Field(default_factory=list)
    recent_crm_notes: list[CrmNoteResponse] = Field(default_factory=list)
