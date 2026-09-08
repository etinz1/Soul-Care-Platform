"""
SQLAlchemy ORM models for the Soul Care Platform MVP.

Fields marked with a trailing `  # PHI:encrypted` comment are stored using an
EncryptedType (see app/db/crypto.py, not included in this excerpt) backed by
envelope encryption against a KMS-managed data key. This file focuses on
schema shape and relationships; wire up the actual encryption TypeDecorator
in your db layer before storing real client data.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class UserRole(str, enum.Enum):
    client = "client"
    coach = "coach"
    provider = "provider"
    church_admin = "church_admin"
    platform_admin = "platform_admin"


class ProviderType(str, enum.Enum):
    psychiatrist = "psychiatrist"
    licensed_counselor = "licensed_counselor"
    addiction_specialist = "addiction_specialist"


class VettingStatus(str, enum.Enum):
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class RiskType(str, enum.Enum):
    suicidal_ideation = "suicidal_ideation"
    substance_abuse = "substance_abuse"
    other_acute = "other_acute"


class RiskSeverity(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    imminent = "imminent"


class ProtocolTriggered(str, enum.Enum):
    safe_t = "safe_t"
    act_model = "act_model"
    addiction_referral = "addiction_referral"
    none = "none"


class ReferralStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    completed = "completed"
    expired = "expired"


class IntakeStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    triaged = "triaged"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    email = Column(String, unique=True, nullable=False)  # PHI:encrypted
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String, nullable=True)  # PHI:encrypted
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class Church(Base):
    __tablename__ = "churches"

    id = uuid_pk()
    name = Column(String, nullable=False)
    tax_id = Column(String, nullable=True)  # PHI:encrypted (PII, not clinical)
    primary_contact_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    billing_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Coach(Base):
    __tablename__ = "coaches"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    bio = Column(Text, nullable=True)
    certifications = Column(JSONB, default=list)
    church_affiliation_id = Column(UUID(as_uuid=True), ForeignKey("churches.id"), nullable=True)
    active = Column(Boolean, default=True)


class ClinicalProvider(Base):
    __tablename__ = "clinical_providers"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    provider_type = Column(Enum(ProviderType), nullable=False)
    license_number = Column(String, nullable=False)  # PHI:encrypted
    license_state = Column(String, nullable=False)
    npi_number = Column(String, nullable=True)  # PHI:encrypted
    malpractice_verified = Column(Boolean, default=False)
    vetting_status = Column(Enum(VettingStatus), default=VettingStatus.pending)
    accepting_referrals = Column(Boolean, default=False)
    onboarded_at = Column(DateTime, nullable=True)


class Client(Base):
    __tablename__ = "clients"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    coach_id = Column(UUID(as_uuid=True), ForeignKey("coaches.id"), nullable=True)
    church_sponsor_id = Column(UUID(as_uuid=True), ForeignKey("churches.id"), nullable=True)
    date_of_birth = Column(String, nullable=True)  # PHI:encrypted
    emergency_contact = Column(String, nullable=True)  # PHI:encrypted
    created_at = Column(DateTime, default=datetime.utcnow)

    intake_assessments = relationship("IntakeAssessment", back_populates="client")


class IntakeAssessment(Base):
    __tablename__ = "intake_assessments"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    status = Column(Enum(IntakeStatus), default=IntakeStatus.draft)
    distress_level = Column(Integer, nullable=True)
    phq9_score = Column(Integer, nullable=True)  # PHI:encrypted
    gad7_score = Column(Integer, nullable=True)  # PHI:encrypted
    protective_factors = Column(JSONB, default=list)
    presenting_concerns = Column(JSONB, default=list)  # e.g. ["anxiety", "grief"]
    raw_responses = Column(JSONB, nullable=True)  # PHI:encrypted (full blob)

    client = relationship("Client", back_populates="intake_assessments")
    risk_events = relationship("RiskEvent", back_populates="intake_assessment")


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = uuid_pk()
    intake_assessment_id = Column(UUID(as_uuid=True), ForeignKey("intake_assessments.id"), nullable=False)
    risk_type = Column(Enum(RiskType), nullable=False)
    severity = Column(Enum(RiskSeverity), nullable=False)
    protocol_triggered = Column(Enum(ProtocolTriggered), default=ProtocolTriggered.none)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)  # PHI:encrypted

    intake_assessment = relationship("IntakeAssessment", back_populates="risk_events")


class RoiConsent(Base):
    __tablename__ = "roi_consents"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    discloses_to_provider_id = Column(UUID(as_uuid=True), ForeignKey("clinical_providers.id"), nullable=True)
    discloses_to_church_id = Column(UUID(as_uuid=True), ForeignKey("churches.id"), nullable=True)
    scope = Column(JSONB, default=dict)
    signed_at = Column(DateTime, default=datetime.utcnow)
    signature_hash = Column(String, nullable=False)  # PHI:encrypted
    document_s3_key = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class Referral(Base):
    __tablename__ = "referrals"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("clinical_providers.id"), nullable=False)
    risk_event_id = Column(UUID(as_uuid=True), ForeignKey("risk_events.id"), nullable=True)
    consent_id = Column(UUID(as_uuid=True), ForeignKey("roi_consents.id"), nullable=False)
    referral_type = Column(String, default="standard")  # standard | urgent | emergency
    status = Column(Enum(ReferralStatus), default=ReferralStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)


class Sponsorship(Base):
    __tablename__ = "sponsorships"

    id = uuid_pk()
    church_id = Column(UUID(as_uuid=True), ForeignKey("churches.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    sponsor_type = Column(String, default="full")  # full | partial | per_session
    sessions_covered = Column(Integer, default=0)
    amount_covered_cents = Column(Integer, default=0)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(String, default="active")


class Invoice(Base):
    __tablename__ = "invoices"

    id = uuid_pk()
    sponsorship_id = Column(UUID(as_uuid=True), ForeignKey("sponsorships.id"), nullable=True)
    church_id = Column(UUID(as_uuid=True), ForeignKey("churches.id"), nullable=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    line_items = Column(JSONB, default=list)  # session dates/counts/amounts ONLY
    stripe_payment_intent_id = Column(String, nullable=True)
    amount_cents = Column(Integer, default=0)
    status = Column(String, default="open")
    issued_at = Column(DateTime, default=datetime.utcnow)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    coach_id = Column(UUID(as_uuid=True), ForeignKey("coaches.id"), nullable=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("clinical_providers.id"), nullable=True)
    session_type = Column(String, nullable=False)  # coaching | prayer | clinical
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String, default="scheduled")

    # Deliberately no forward FK to session_notes here: a session can carry
    # more than one note (e.g. a spiritual_action_plan note AND a progress
    # note), and a forward + backward FK pair between these two tables would
    # create a circular dependency that breaks migration table-creation
    # order. Look up a session's notes via `session_notes.session_id`.
    notes = relationship("SessionNote", back_populates="session")


class SessionNote(Base):
    __tablename__ = "session_notes"

    id = uuid_pk()
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    note_type = Column(String, nullable=False)  # spiritual_action_plan | progress | clinical
    encrypted_content = Column(Text, nullable=False)  # PHI:encrypted
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SessionRecord", back_populates="notes")


class PrayerRequest(Base):
    __tablename__ = "prayer_requests"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    request_text = Column(Text, nullable=False)  # PHI:encrypted
    urgency = Column(String, default="routine")  # routine | urgent | immediate
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)


class ScriptureTag(Base):
    __tablename__ = "scripture_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)


class ScriptureContent(Base):
    __tablename__ = "scripture_content"

    id = uuid_pk()
    tag_id = Column(Integer, ForeignKey("scripture_tags.id"), nullable=False)
    reference = Column(String, nullable=False)
    verse_text = Column(Text, nullable=False)
    reflection_text = Column(Text, nullable=True)
    translation = Column(String, default="ESV")


class ScriptureDelivery(Base):
    __tablename__ = "scripture_deliveries"

    id = uuid_pk()
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    scripture_content_id = Column(UUID(as_uuid=True), ForeignKey("scripture_content.id"), nullable=False)
    channel = Column(String, default="dashboard")  # dashboard | email | sms
    triggered_by_intake_id = Column(UUID(as_uuid=True), ForeignKey("intake_assessments.id"), nullable=True)
    delivered_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Append-only. Grant only INSERT to the application's DB role in production."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    phi_accessed = Column(Boolean, default=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)
