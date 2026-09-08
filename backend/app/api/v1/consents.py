"""
Release of Information (ROI) consent — the client-facing half of the "Refer"
module's privacy control (SECURITY_GRC_BLUEPRINT.md §5). A referral cannot
be created without a valid, unexpired, unrevoked consent scoped to the
receiving provider — see api/v1/referrals.py.
"""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user
from app.db import get_db_session
from app.models import Church, Client, ClinicalProvider, RoiConsent, User, UserRole
from app.schemas import ConsentCreateRequest, ConsentResponse
from app.security import hash_typed_signature

router = APIRouter(prefix="/consents/roi", tags=["consents"])


def _to_response(consent: RoiConsent) -> ConsentResponse:
    return ConsentResponse(
        consent_id=consent.id,
        client_id=consent.client_id,
        discloses_to_provider_id=consent.discloses_to_provider_id,
        discloses_to_church_id=consent.discloses_to_church_id,
        scope=consent.scope,
        signed_at=consent.signed_at,
        expires_at=consent.expires_at,
        revoked_at=consent.revoked_at,
    )


async def _authorize_client_ownership(db: AsyncSession, current_user: User, client_id: UUID) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if current_user.role == UserRole.client and client.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot act on another client's consent")
    if current_user.role not in (UserRole.client, UserRole.platform_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")
    return client


@router.post("", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def create_consent(
    payload: ConsentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    await _authorize_client_ownership(db, current_user, payload.client_id)

    if payload.discloses_to_provider_id is not None:
        provider = await db.get(ClinicalProvider, payload.discloses_to_provider_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    if payload.discloses_to_church_id is not None:
        church = await db.get(Church, payload.discloses_to_church_id)
        if church is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Church not found")

    signed_at = datetime.utcnow()
    signature_hash = hash_typed_signature(
        payload.client_id, payload.typed_signature_name, payload.scope, signed_at
    )

    consent = RoiConsent(
        client_id=payload.client_id,
        discloses_to_provider_id=payload.discloses_to_provider_id,
        discloses_to_church_id=payload.discloses_to_church_id,
        scope=payload.scope,
        signed_at=signed_at,
        signature_hash=signature_hash,
        expires_at=signed_at + timedelta(days=payload.expires_in_days),
    )
    db.add(consent)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="consent.created",
        resource_type="roi_consents",
        resource_id=str(consent.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(consent)


@router.get("/{consent_id}", response_model=ConsentResponse)
async def get_consent(
    consent_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    consent = await db.get(RoiConsent, consent_id)
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")

    client = await db.get(Client, consent.client_id)
    is_owning_client = current_user.role == UserRole.client and client is not None and client.user_id == current_user.id

    is_disclosed_provider = False
    if consent.discloses_to_provider_id is not None:
        provider = await db.get(ClinicalProvider, consent.discloses_to_provider_id)
        is_disclosed_provider = provider is not None and provider.user_id == current_user.id

    is_admin = current_user.role == UserRole.platform_admin

    if not (is_owning_client or is_disclosed_provider or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this consent")

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="consent.viewed",
        resource_type="roi_consents",
        resource_id=str(consent.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(consent)


@router.post("/{consent_id}/revoke", response_model=ConsentResponse)
async def revoke_consent(
    consent_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    consent = await db.get(RoiConsent, consent_id)
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")

    await _authorize_client_ownership(db, current_user, consent.client_id)

    if consent.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Consent already revoked")

    consent.revoked_at = datetime.utcnow()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="consent.revoked",
        resource_type="roi_consents",
        resource_id=str(consent.id),
        phi_accessed=True,
    )
    await db.commit()
    return _to_response(consent)
