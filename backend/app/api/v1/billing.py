"""
Billing: invoice creation (platform-admin/ops only — churches and clients
only ever *read* invoices, via GET /church/invoices) and the Stripe webhook
receiver that reconciles payment status.

STRIPE INTEGRATION STATUS — pre-launch caveat (see README.md): this
implements Stripe's webhook *signature verification* algorithm directly
(app.security.verify_stripe_webhook_signature) so the endpoint is real and
testable, but nothing here calls the Stripe API to actually create a
PaymentIntent or Checkout Session — that's the other half of a real
integration and is intentionally out of scope for this scaffold. Set
STRIPE_WEBHOOK_SECRET before this endpoint is pointed at a live Stripe
webhook; with it unset, signature verification is skipped entirely, which
must never happen in production.
"""
import json
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import require_role
from app.db import get_db_session
from app.models import Church, Client, Invoice, Sponsorship, User, UserRole
from app.schemas import InvoiceCreateRequest, InvoiceResponse
from app.security import verify_stripe_webhook_signature

router = APIRouter(prefix="/billing", tags=["billing"])

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")


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


@router.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: InvoiceCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    if payload.church_id is not None and await db.get(Church, payload.church_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Church not found")
    if payload.client_id is not None and await db.get(Client, payload.client_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    if payload.sponsorship_id is not None:
        sponsorship = await db.get(Sponsorship, payload.sponsorship_id)
        if sponsorship is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sponsorship not found")
        if payload.church_id is not None and sponsorship.church_id != payload.church_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Sponsorship does not belong to this church"
            )
        if payload.client_id is not None and sponsorship.client_id != payload.client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Sponsorship does not belong to this client"
            )

    # Computed from line items server-side — never trust a client-supplied
    # total, and line items are structurally billing-only (see
    # InvoiceLineItem's docstring: no diagnosis/notes field exists to leak).
    amount_cents = sum(item.amount_cents for item in payload.line_items)
    line_items_json = [item.model_dump(mode="json") for item in payload.line_items]

    invoice = Invoice(
        sponsorship_id=payload.sponsorship_id,
        church_id=payload.church_id,
        client_id=payload.client_id,
        line_items=line_items_json,
        amount_cents=amount_cents,
        status="open",
    )
    db.add(invoice)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="invoice.created",
        resource_type="invoices",
        resource_id=str(invoice.id),
        phi_accessed=False,
    )
    await db.commit()
    return _invoice_to_response(invoice)


async def _find_invoice_for_event(db: AsyncSession, data_object: dict) -> Optional[Invoice]:
    metadata = data_object.get("metadata") or {}
    invoice_id = metadata.get("invoice_id")
    if invoice_id:
        try:
            invoice = await db.get(Invoice, UUID(invoice_id))
            if invoice is not None:
                return invoice
        except ValueError:
            pass

    payment_intent_id = data_object.get("id")
    if payment_intent_id:
        return (
            await db.execute(select(Invoice).where(Invoice.stripe_payment_intent_id == payment_intent_id))
        ).scalar_one_or_none()
    return None


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db_session)):
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if STRIPE_WEBHOOK_SECRET:
        if not verify_stripe_webhook_signature(raw_body, sig_header, STRIPE_WEBHOOK_SECRET):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature")
    # else: STRIPE_WEBHOOK_SECRET is unset — signature verification is
    # skipped (dev/test only; see module docstring). This must be set
    # before this endpoint is wired to a real Stripe webhook.

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}
    payment_intent_id = data_object.get("id")

    invoice = await _find_invoice_for_event(db, data_object)
    if invoice is not None:
        if event_type == "payment_intent.succeeded" and invoice.status != "paid":
            invoice.status = "paid"
            invoice.stripe_payment_intent_id = payment_intent_id
            await write_audit_log(
                db,
                actor_user_id=None,
                action="invoice.paid",
                resource_type="invoices",
                resource_id=str(invoice.id),
                phi_accessed=False,
            )
            await db.commit()
        elif event_type == "payment_intent.payment_failed":
            invoice.status = "payment_failed"
            await write_audit_log(
                db,
                actor_user_id=None,
                action="invoice.payment_failed",
                resource_type="invoices",
                resource_id=str(invoice.id),
                phi_accessed=False,
            )
            await db.commit()

    # Always 200 on a well-formed, verified event — even one we didn't act
    # on — so Stripe doesn't retry-storm an event we simply don't handle.
    return {"received": True}
