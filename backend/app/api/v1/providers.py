"""
Clinical provider onboarding/vetting. Only /providers/{id}/vetting is
implemented here — it exists mainly to demonstrate `require_role` enforcing
RBAC end-to-end (platform_admin only), per SECURITY_GRC_BLUEPRINT.md §1 and
§4's provider-vetting control.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import write_audit_log
from app.auth import require_role
from app.db import get_db_session
from app.models import ClinicalProvider, User, UserRole, VettingStatus
from pydantic import BaseModel

router = APIRouter(prefix="/providers", tags=["providers"])


class VettingDecision(BaseModel):
    vetting_status: VettingStatus
    accepting_referrals: bool = False


@router.patch("/{provider_id}/vetting")
async def update_vetting_status(
    provider_id: UUID,
    decision: VettingDecision,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_role(UserRole.platform_admin)),
):
    """Admin-only: approve/reject/suspend a clinical provider's network membership."""
    provider = await db.get(ClinicalProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    provider.vetting_status = decision.vetting_status
    # A provider can only accept referrals once approved, regardless of what
    # the caller passes — this check lives here, not just in the schema.
    provider.accepting_referrals = decision.accepting_referrals and decision.vetting_status == VettingStatus.approved

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="provider.vetting_updated",
        resource_type="clinical_providers",
        resource_id=str(provider.id),
        phi_accessed=False,
        request=request,
    )
    await db.commit()
    return {
        "provider_id": str(provider.id),
        "vetting_status": provider.vetting_status.value,
        "accepting_referrals": provider.accepting_referrals,
    }
