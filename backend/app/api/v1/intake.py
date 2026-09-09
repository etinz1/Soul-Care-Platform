"""
FastAPI router for the Smart Intake & Risk Assessment module.

POST /api/v1/intake/{intake_id}/submit is the module's centerpiece: it
validates the intake payload, runs the deterministic risk engine, and —
inside a single DB transaction — persists the intake, writes a RiskEvent
when a hard-stop condition fires, creates the routed Referral, and kicks off
scripture delivery. Every step is audit-logged.
"""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user, require_role
from app.db import get_db_session
from app.models import (
    ClinicalProvider,
    Client,
    Coach,
    IntakeAssessment,
    IntakeStatus,
    Referral,
    RiskEvent,
    RoiConsent,
    User,
    UserRole,
)
from app.schemas import (
    IntakeCreateRequest,
    IntakeDetailResponse,
    IntakeDraftResponse,
    IntakeSubmission,
    IntakeSubmitResponse,
    RiskDecision,
)
from app.services import risk_engine, scripture_engine

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("", response_model=IntakeDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_intake_draft(
    payload: IntakeCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Create a draft assessment to submit into. Kept intentionally minimal —
    the real content only lands on submit (see submit_intake below)."""
    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    _authorize_submission(current_user, client)

    intake = IntakeAssessment(client_id=payload.client_id, status=IntakeStatus.draft)
    db.add(intake)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="intake.draft_created",
        resource_type="intake_assessments",
        resource_id=str(intake.id),
        phi_accessed=False,
    )
    await db.commit()
    return IntakeDraftResponse(intake_id=intake.id, client_id=intake.client_id, status=intake.status.value)


@router.get("/{intake_id}", response_model=IntakeDetailResponse)
async def get_intake(
    intake_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    intake = await db.get(IntakeAssessment, intake_id)
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake assessment not found")

    client = await db.get(Client, intake.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    is_self = current_user.role == UserRole.client and client.user_id == current_user.id
    is_admin = current_user.role == UserRole.platform_admin
    is_own_coach = False
    if current_user.role == UserRole.coach:
        coach = (await db.execute(select(Coach).where(Coach.user_id == current_user.id))).scalar_one_or_none()
        is_own_coach = coach is not None and client.coach_id == coach.id

    if not (is_self or is_admin or is_own_coach):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this intake assessment")

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="intake.viewed",
        resource_type="intake_assessments",
        resource_id=str(intake.id),
        phi_accessed=True,
    )
    await db.commit()

    return IntakeDetailResponse(
        intake_id=intake.id,
        client_id=intake.client_id,
        status=intake.status.value,
        submitted_at=intake.submitted_at,
        distress_level=intake.distress_level,
        presenting_concerns=intake.presenting_concerns or [],
        protective_factors=intake.protective_factors or [],
    )


@router.post("/{intake_id}/submit", response_model=IntakeSubmitResponse)
async def submit_intake(
    intake_id: UUID,
    payload: IntakeSubmission,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a completed intake assessment.

    Access control: a client may only submit their own intake; a coach may
    submit on behalf of an assigned client only in an assisted-intake flow
    (not shown here) — the ownership check below covers the common client
    self-submit path.
    """
    intake = await db.get(IntakeAssessment, intake_id)
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake assessment not found")
    if intake.status == IntakeStatus.submitted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Intake already submitted")

    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    _authorize_submission(current_user, client)

    # --- 1. Persist the intake content ---
    intake.status = IntakeStatus.submitted
    intake.submitted_at = datetime.utcnow()
    intake.distress_level = payload.distress_level
    intake.phq9_score = payload.phq9_score
    intake.gad7_score = payload.gad7_score
    intake.protective_factors = payload.protective_factors
    intake.presenting_concerns = [c.value for c in payload.presenting_concerns]
    intake.raw_responses = payload.raw_responses

    # --- 2. Run the deterministic risk engine ---
    result = risk_engine.evaluate(payload)

    risk_decision = RiskDecision(
        risk_type=result.risk_type,
        severity=result.severity,
        protocol_triggered=result.protocol_triggered,
        is_hard_stop=result.is_hard_stop,
        routed_provider_type=result.routed_provider_type,
        message=result.message,
    )

    if result.risk_type is not None:
        risk_event = RiskEvent(
            intake_assessment_id=intake.id,
            risk_type=result.risk_type,
            severity=result.severity,
            protocol_triggered=result.protocol_triggered,
        )
        db.add(risk_event)
        await db.flush()  # get risk_event.id without committing

        await write_audit_log(
            db,
            actor_user_id=current_user.id,
            action="risk_event.triggered",
            resource_type="risk_events",
            resource_id=str(risk_event.id),
            phi_accessed=True,
            request=request,
        )

        # --- 3. Route to an available provider of the correct type ---
        provider = await _find_available_provider(db, result.routed_provider_type)
        if provider is not None:
            consent = await _get_or_create_emergency_consent(
                db, client_id=client.id, provider_id=provider.id, urgency=result.referral_urgency
            )
            referral = Referral(
                client_id=client.id,
                provider_id=provider.id,
                risk_event_id=risk_event.id,
                consent_id=consent.id,
                referral_type=result.referral_urgency or "standard",
            )
            db.add(referral)
            await db.flush()
            risk_decision.referral_id = referral.id

            await write_audit_log(
                db,
                actor_user_id=current_user.id,
                action="referral.auto_created",
                resource_type="referrals",
                resource_id=str(referral.id),
                phi_accessed=True,
                request=request,
            )
            # Notification dispatch (SMS/pager to provider on-call) is
            # enqueued here in production, e.g.:
            # notify_queue.send_task("notify_provider_of_referral", args=[str(referral.id)])
        else:
            # No provider of the required type currently available: this must
            # escalate to a human on-call coordinator immediately — never
            # silently fail a hard-stop routing. Wire to your paging system.
            await write_audit_log(
                db,
                actor_user_id=current_user.id,
                action="referral.no_provider_available_escalation",
                resource_type="risk_events",
                resource_id=str(risk_event.id),
                phi_accessed=True,
                request=request,
            )

    # --- 4. Scripture automation (runs regardless of risk outcome) ---
    suppress_sync = result.severity == "imminent"
    scripture_result = await scripture_engine.dispatch(
        db,
        client_id=client.id,
        presenting_concerns=payload.presenting_concerns,
        intake_id=intake.id,
        suppress_synchronous_display=suppress_sync,
    )

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="intake.submit",
        resource_type="intake_assessments",
        resource_id=str(intake.id),
        phi_accessed=True,
        request=request,
    )

    await db.commit()

    return IntakeSubmitResponse(
        intake_id=intake.id,
        status=intake.status.value,
        submitted_at=intake.submitted_at,
        risk_decision=risk_decision,
        scripture_cards=scripture_result.cards_for_response,
    )


def _authorize_submission(current_user: User, client: Client) -> None:
    if current_user.role == UserRole.client and client.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot submit intake for another client")
    if current_user.role not in (UserRole.client, UserRole.coach, UserRole.platform_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to submit intake")


async def _find_available_provider(db: AsyncSession, provider_type: str | None) -> ClinicalProvider | None:
    if provider_type is None:
        return None
    stmt = (
        select(ClinicalProvider)
        .where(ClinicalProvider.provider_type == provider_type)
        .where(ClinicalProvider.accepting_referrals.is_(True))
        .where(ClinicalProvider.vetting_status == "approved")
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_or_create_emergency_consent(
    db: AsyncSession, client_id: UUID, provider_id: UUID, urgency: str | None
) -> RoiConsent:
    """
    Hard-stop referrals (urgent/emergency) proceed under HIPAA's emergency
    treatment exception (45 CFR 164.512(j) — averting a serious and imminent
    threat to health or safety) rather than blocking a crisis referral behind
    a signature flow. This still creates an explicit, scoped, audited consent
    record — it is a documented emergency disclosure, not an unlogged
    bypass — and the client is asked to countersign a standard ROI at the
    first following session. Legal/compliance should review this pattern
    before launch; it is the single most sensitive judgment call in this
    module.
    """
    consent = RoiConsent(
        client_id=client_id,
        discloses_to_provider_id=provider_id,
        scope={"basis": "emergency_exception_164_512_j", "clinical_summary": True},
        signature_hash="EMERGENCY_EXCEPTION_NO_SIGNATURE_ON_FILE",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(consent)
    await db.flush()
    return consent
