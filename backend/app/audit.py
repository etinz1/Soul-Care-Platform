"""
Audit logging helper — every PHI-touching action in the API layer should
call this so `audit_logs` stays the reliable source of truth described in
SECURITY_GRC_BLUEPRINT.md §3. The DB role used by the app should have
INSERT-only privileges on this table in production (no UPDATE/DELETE).
"""
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_user_id,
    action: str,
    resource_type: str,
    resource_id: str | None,
    phi_accessed: bool,
    request: Request | None = None,
) -> None:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        phi_accessed=phi_accessed,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(entry)
    # Intentionally not committed here — caller commits as part of the
    # surrounding transaction so audit rows and business data are atomic.
