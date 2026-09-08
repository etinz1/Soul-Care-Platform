"""
Church sponsorship + billing visibility — ARCHITECTURE.md §7 step 7. This is
the module that has to hold the line on "billing without clinical
visibility" (§3): a church can see sponsorships and invoices for the
clients it sponsors, and NOTHING else about those clients — no intake,
risk, referral, or session-note data is reachable from here or from the
`churches` table's FKs at all.

Church provisioning (`POST /church`) is admin-only rather than
self-service, matching providers.py's vetted-onboarding posture but
without a public signup step: churches are onboarded by platform staff.
Invoice *creation* lives in api/v1/billing.py; this file only covers the
church-facing read surface for invoices, per the API routing table.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import get_current_user, require_role
from app.db import get_db_session
from app.models import Church, Client, Invoice, RoiConsent, Sponsorship, User, UserRole
from app.schemas import (
    ChurchCreateRequest,
    ChurchResponse,
    InvoiceResponse,
    SponsorshipCreateRequest,
    SponsorshipResponse,
    SponsorshipUpdateRequest,
)

router = APIRouter(prefix="/church", tags=["church"])


def _church_to_response(church: Church) -> ChurchResponse:
    return ChurchResponse(
        church_id=church.id,
        name=church.name,
        billing_email=church.billing_email,
        primary_contact_user_id=church.primary_contact_user_id,
        created_at=church.created_at,
    )


def _sponsorship_to_response(s: Sponsorship) -> SponsorshipResponse:
    return SponsorshipResponse(
        sponsorship_id=s.id,
        church_id=s.church_id,
        client_id=s.client_id,
        sponsor_type=s.sponsor_type,
        sessions_covered=s.sessions_covered,
        amount_covered_cents=s.amount_covered_cents,
        start_date=s.start_date,
        end_date=s.end_date,
        status=s.status,
    )


def _invoice_to_response(inv: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        invoice_id=inv.id,
        sponsorship_id=inv.sponsorship_id,
        church_id=inv.church_id,
        client_id=inv.client_id,
        line_items=inv.line_items or [],
        amount_cents=inv.amount_cents,
        status=inv.status,
        stripe_payment_intent_id=inv.stripe_payment_intent_id,
        issued_at=inv.issued_at,
    )


async def _get_own_church_as_admin(db: AsyncSession, user: User) -> Optional[Church]:
    if user.role != UserRole.church_admin:
        return None
    return (
        await db.execute(select(Church).where(Church.primary_contact_user_id == user.id))
    ).scalar_one_or_none()


async def _authorize_church_admin(db: AsyncSession, current_user: User, church_id: UUID) -> Church:
    church = await db.get(Church, church_id)
    if church is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Church not found")
    if current_user.role == UserRole.platform_admin:
        return church
    if current_user.role == UserRole.church_admin and church.primary_contact_user_id == current_user.id:
        return church
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to act on this church")


@router.post("", response_model=ChurchResponse, status_code=status.HTTP_201_CREATED)
async def create_church(
    payload: ChurchCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    if payload.primary_contact_user_id is not None:
        contact = await db.get(User, payload.primary_contact_user_id)
        if contact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="primary_contact_user_id not found")
        if contact.role != UserRole.church_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="primary_contact_user_id must belong to a user with role=church_admin",
            )

    church = Church(
        name=payload.name,
        tax_id=payload.tax_id,
        billing_email=payload.billing_email,
        primary_contact_user_id=payload.primary_contact_user_id,
    )
    db.add(church)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="church.created",
        resource_type="churches",
        resource_id=str(church.id),
        phi_accessed=False,
    )
    await db.commit()
    return _church_to_response(church)


@router.post("/sponsorships", response_model=SponsorshipResponse, status_code=status.HTTP_201_CREATED)
async def create_sponsorship(
    payload: SponsorshipCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    await _authorize_church_admin(db, current_user, payload.church_id)

    client = await db.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    consent = await db.get(RoiConsent, payload.consent_id)
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")
    if consent.client_id != payload.client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent does not belong to this client")
    if consent.discloses_to_church_id != payload.church_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is not scoped to this church")
    if consent.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent has been revoked")
    if consent.expires_at is not None and consent.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent has expired")

    sponsorship = Sponsorship(
        church_id=payload.church_id,
        client_id=payload.client_id,
        sponsor_type=payload.sponsor_type,
        sessions_covered=payload.sessions_covered,
        amount_covered_cents=payload.amount_covered_cents,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="active",
    )
    db.add(sponsorship)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="sponsorship.created",
        resource_type="sponsorships",
        resource_id=str(sponsorship.id),
        phi_accessed=False,
    )
    await db.commit()
    return _sponsorship_to_response(sponsorship)


@router.get("/sponsorships", response_model=list[SponsorshipResponse])
async def list_sponsorships(
    church_id: Optional[UUID] = Query(None),
    client_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Sponsorship)

    if current_user.role == UserRole.client:
        client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
        if client is None:
            return []
        stmt = stmt.where(Sponsorship.client_id == client.id)
    elif current_user.role == UserRole.church_admin:
        own_church = await _get_own_church_as_admin(db, current_user)
        if own_church is None:
            return []
        stmt = stmt.where(Sponsorship.church_id == own_church.id)
    elif current_user.role == UserRole.platform_admin:
        if church_id is not None:
            stmt = stmt.where(Sponsorship.church_id == church_id)
        if client_id is not None:
            stmt = stmt.where(Sponsorship.client_id == client_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list sponsorships")

    sponsorships = (await db.execute(stmt)).scalars().all()
    return [_sponsorship_to_response(s) for s in sponsorships]


async def _authorize_sponsorship_view(db: AsyncSession, current_user: User, sponsorship: Sponsorship) -> None:
    if current_user.role == UserRole.platform_admin:
        return
    if current_user.role == UserRole.church_admin:
        church = await db.get(Church, sponsorship.church_id)
        if church is not None and church.primary_contact_user_id == current_user.id:
            return
    if current_user.role == UserRole.client:
        client = await db.get(Client, sponsorship.client_id)
        if client is not None and client.user_id == current_user.id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this sponsorship")


@router.get("/sponsorships/{sponsorship_id}", response_model=SponsorshipResponse)
async def get_sponsorship(
    sponsorship_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    sponsorship = await db.get(Sponsorship, sponsorship_id)
    if sponsorship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sponsorship not found")
    await _authorize_sponsorship_view(db, current_user, sponsorship)
    return _sponsorship_to_response(sponsorship)


@router.patch("/sponsorships/{sponsorship_id}", response_model=SponsorshipResponse)
async def update_sponsorship(
    sponsorship_id: UUID,
    payload: SponsorshipUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    sponsorship = await db.get(Sponsorship, sponsorship_id)
    if sponsorship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sponsorship not found")

    # Reuses the church-ownership check, not the read-visibility check: a
    # client can view their own sponsorship but never edit it.
    await _authorize_church_admin(db, current_user, sponsorship.church_id)

    if payload.status is not None:
        sponsorship.status = payload.status
    if payload.end_date is not None:
        sponsorship.end_date = payload.end_date

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="sponsorship.updated",
        resource_type="sponsorships",
        resource_id=str(sponsorship.id),
        phi_accessed=False,
    )
    await db.commit()
    return _sponsorship_to_response(sponsorship)


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_church_invoices(
    church_id: Optional[UUID] = Query(None),
    client_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Billing detail only — Invoice has no FK path to any clinical table (see module docstring)."""
    stmt = select(Invoice)

    if current_user.role == UserRole.client:
        client = (await db.execute(select(Client).where(Client.user_id == current_user.id))).scalar_one_or_none()
        if client is None:
            return []
        stmt = stmt.where(Invoice.client_id == client.id)
    elif current_user.role == UserRole.church_admin:
        own_church = await _get_own_church_as_admin(db, current_user)
        if own_church is None:
            return []
        stmt = stmt.where(Invoice.church_id == own_church.id)
    elif current_user.role == UserRole.platform_admin:
        if church_id is not None:
            stmt = stmt.where(Invoice.church_id == church_id)
        if client_id is not None:
            stmt = stmt.where(Invoice.client_id == client_id)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to list invoices")

    if status_filter is not None:
        stmt = stmt.where(Invoice.status == status_filter)

    invoices = (await db.execute(stmt)).scalars().all()
    return [_invoice_to_response(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_church_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    is_admin = current_user.role == UserRole.platform_admin
    is_owning_church = False
    if current_user.role == UserRole.church_admin and invoice.church_id is not None:
        church = await db.get(Church, invoice.church_id)
        is_owning_church = church is not None and church.primary_contact_user_id == current_user.id
    is_owning_client = False
    if current_user.role == UserRole.client and invoice.client_id is not None:
        client = await db.get(Client, invoice.client_id)
        is_owning_client = client is not None and client.user_id == current_user.id

    if not (is_admin or is_owning_church or is_owning_client):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to view this invoice")

    return _invoice_to_response(invoice)
