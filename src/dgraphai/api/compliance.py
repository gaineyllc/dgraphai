"""Compliance report generation API."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.dgraphai.db.alert_models import ComplianceReport
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.compliance.reports import ReportGenerator, REPORT_DEFINITIONS
from src.dgraphai.api.license import gate_feature

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/report-types")
async def list_report_types(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict[str, str]]:
    """List available compliance report types."""
    return [
        {"id": k, "title": v["title"], "description": v["description"]}
        for k, v in REPORT_DEFINITIONS.items()
    ]


@router.post("/reports/{report_type}")
async def generate_report(
    report_type: str,
    background:  BackgroundTasks,
    format:      str = "json",
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
    _:           None = Depends(gate_feature("compliance_reports")),
) -> dict[str, Any]:
    """Trigger async generation of a compliance report."""
    if report_type not in REPORT_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    report = ComplianceReport(
        tenant_id   = auth.tenant_id,
        report_type = report_type,
        title       = REPORT_DEFINITIONS[report_type]["title"],
        format      = format,
        generated_by = auth.user_id,
        status      = "pending",
    )
    db.add(report)
    await db.flush()
    report_id = str(report.id)

    background.add_task(_generate_report, report_id, str(auth.tenant_id), format)
    return {"report_id": report_id, "status": "pending",
            "message": f"Poll GET /api/compliance/reports/{report_id} for results"}


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    auth:      AuthContext = Depends(get_auth_context),
    db:        AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(ComplianceReport).where(
            ComplianceReport.id == uuid.UUID(report_id),
            ComplianceReport.tenant_id == auth.tenant_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": str(r.id), "report_type": r.report_type, "title": r.title,
        "status": r.status, "format": r.format, "row_count": r.row_count,
        "findings": r.findings, "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "error": r.error,
    }


@router.get("/reports")
async def list_reports(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(ComplianceReport).where(ComplianceReport.tenant_id == auth.tenant_id)
        .order_by(ComplianceReport.generated_at.desc()).limit(50)
    )
    return [{"id": str(r.id), "report_type": r.report_type, "title": r.title,
             "status": r.status, "row_count": r.row_count,
             "generated_at": r.generated_at.isoformat() if r.generated_at else None}
            for r in result.scalars().all()]


async def _generate_report(report_id: str, tenant_id: str, fmt: str) -> None:
    from src.dgraphai.db.session import AsyncSessionLocal
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    import uuid as _uuid

    async with AsyncSessionLocal() as db:
        tenant_r = await db.execute(select(Tenant).where(Tenant.id == _uuid.UUID(tenant_id)))
        tenant   = tenant_r.scalar_one_or_none()
        report_r = await db.execute(select(ComplianceReport).where(ComplianceReport.id == _uuid.UUID(report_id)))
        report   = report_r.scalar_one_or_none()
        if not report or not tenant:
            return

        report.status = "running"
        await db.commit()

        try:
            backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
            gen     = ReportGenerator()
            result  = await gen.generate(report.report_type, _uuid.UUID(tenant_id), backend, fmt)

            report.status       = "complete"
            report.findings     = {k: len(v) for k, v in result.get("findings", {}).items()}
            report.row_count    = result.get("total_findings", 0)
            report.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            report.status = "error"
            report.error  = str(e)
        await db.commit()
