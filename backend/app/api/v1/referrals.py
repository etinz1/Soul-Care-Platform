"""
Referral marketplace: client-initiated, non-crisis referrals to a vetted
clinical provider. (The crisis/hard-stop path — auto-created referrals under
the emergency-treatment exception — lives in api/v1/intake.py, not here.)

A referral can only be created against a provider who is approved AND
currently accepting referrals, and only when a valid, unexpired, unrevoked
ROI consent already exists scoped to that specific provider — enforced here
in addition to the DB-level FK, per SECURITY_GRC_BLUEPRINT.md §5.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user
from app.db import get_db_session
from app.models import Client, ClinicalProvider, Referral, ReferralStatus, RoiConsent, User, UserRole, VettingStatus
from app.schemas import ReferralCreateRequest, ReferralRespondRequest, ReferralResponse

router = APIRouter(prefix="/referrals", tags=["referrals"])


async def _to_response(db: AsyncSession, referral: Referral) -> ReferralResponse:
    consent = await db.get(RoiConsent, referral.consent_id)
    return ReferralResponse(
        referral_id=referral.id,
        client_id=referral.client_id,
        provider_id=referral.provider_id,
        referral_type=referral.referral_type,
        status=referral.status.value,
        created_at=referral.created_at,
        consent_id=referral.consent_id,
        roi_scope=(consent.scope if consent is not None else {}),
    )


@router.post("", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: ReferralCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if current_user.role == UserRole.client and client.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot refer another client")
    if current_user.role not in (UserRole.client, UserRole.platform_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to create a referral")

    provider = await db.get(ClinicalProvider, payload.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if provider.vetting_status != VettingStatus.approved or not provider.accepting_referrals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Provider is not currently accepting referrals"
        )

    consent = await db.get(RoiConsent, payload.consent_id)
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")
    if consent.client_id != payload.client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent does not belong to this client")
    if consent.discloses_to_provider_id != payload.provider_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is not scoped to this provider"
        )
    if consent.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent has been revoked")
    if consent.expires_at is not None and consent.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent has expired")

    referral = Referral(
        client_id=payload.client_id,
        provider_id=payload.provider_id,
        consent_id=payload.consent_id,
        referral_type=payload.referral_type,
        status=ReferralStatus.pending,
    )
    db.add(referral)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="referral.created",
        resource_type="referrals",
        resource_id=str(referral.id),
        phi_accessed=True,
    )
    await db.commit()
    return await _to_response(db, referral)


@router.get("", response_model=list[ReferralResponse])
async def list_referrals(
    client_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Role-scoped: a client sees only their own referrals, a provider sees only referrals routed to them."""
    stmt = select(Referral)

    if current_user.role == UserRole.client:
        client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
        if client is None:
            return []
        stmt = stmt.where(Referral.client_id == client.id)
    elif current_user.role == UserRole.provider:
        provider = (
            await db.execute(select(ClinicalProvider).where(ClinicalProvider.user_id == current_user.id))
        ).scalar_one_or_none()
        if provider is None:
            return []
        stmt = stmt.where(Referral.provider_id == provider.id)
    elif current_user.role == UserRole.platform_admin:
        if client_id is not None:
            stmt = stmt.where(Referral.client_id == client_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list referrals")

    referrals = (await db.execute(stmt)).scalars().all()
    return [await _to_response(db, r) for r in referrals]


@router.patch("/{referral_id}/respond", response_model=ReferralResponse)
async def respond_to_referral(
    referral_id: UUID,
    payload: ReferralRespondRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    referral = await db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")

    provider = await db.get(ClinicalProvider, referral.provider_id)
    if provider is None or provider.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the recipient of this referral")

    if referral.status != ReferralStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Referral has already been responded to")

    referral.status = ReferralStatus.accepted if payload.status == "accepted" else ReferralStatus.declined
    referral.responded_at = datetime.utcnow()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="referral.responded",
        resource_type="referrals",
        resource_id=str(referral.id),
        phi_accessed=True,
    )
    await db.commit()
    return await _to_response(db, referral)
