"""
License API — status and feature enforcement.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.licensing.license import (
    LicenseError, get_license, require_feature
)

router = APIRouter(prefix="/api/license", tags=["license"])


@router.get("/status")
async def license_status(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """
    Return current license status.
    Shows features, limits, expiry. Never returns license key material.
    """
    try:
        lic = get_license()
    except LicenseError as e:
        raise HTTPException(status_code=402, detail=str(e))

    days_left = lic.days_until_expiry()

    return {
        "license_id":    lic.license_id,
        "issued_to":     lic.issued_to,
        "license_type":  lic.license_type,
        "is_valid":      lic.is_valid,
        "is_expired":    lic.is_expired,
        "in_grace_period": lic.is_in_grace_period,
        "expires_at":    lic.expires_at.isoformat() if lic.expires_at else None,
        "days_until_expiry": days_left,
        "is_dev_license": lic.metadata.get("dev_mode", False),
        "features": {
            "graph_visualization":  lic.features.graph_visualization,
            "saved_queries":        lic.features.saved_queries,
            "approval_workflows":   lic.features.approval_workflows,
            "scanner_agents":       lic.features.scanner_agents,
            "ai_training_export":   lic.features.ai_training_export,
            "sso_oidc":             lic.features.sso_oidc,
            "custom_roles":         lic.features.custom_roles,
            "audit_log_stream":     lic.features.audit_log_stream,
            "api_access":           lic.features.api_access,
            "compliance_reports":   lic.features.compliance_reports,
        },
        "limits": {
            "max_tenants":    lic.limits.max_tenants,
            "max_users":      lic.limits.max_users,
            "max_connectors": lic.limits.max_connectors,
            "max_nodes":      lic.limits.max_nodes,
            "max_exports":    lic.limits.max_exports,
        },
        "warnings": _build_warnings(lic, days_left),
    }


def _build_warnings(lic: Any, days_left: int | None) -> list[str]:
    warnings = []
    if lic.metadata.get("dev_mode"):
        warnings.append("Running with developer license — not for production use")
    if lic.is_in_grace_period:
        warnings.append(f"License expired — in grace period. Renew immediately.")
    elif days_left is not None and days_left <= 30:
        warnings.append(f"License expires in {days_left} days. Renew soon.")
    if lic.features.scanner_agents == 1:
        warnings.append("Only 1 scanner agent allowed — upgrade for more")
    return warnings


# ── Feature gate middleware helper ────────────────────────────────────────────

def gate_feature(feature: str):
    """
    FastAPI dependency — raises 402 if feature not licensed.

    Usage:
        @router.post("/export")
        async def export(
            auth = Depends(get_auth_context),
            _    = Depends(gate_feature("ai_training_export")),
        ):
    """
    async def _check():
        try:
            require_feature(feature)
        except LicenseError as e:
            raise HTTPException(status_code=402, detail=str(e))
    return _check
