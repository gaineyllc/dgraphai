"""
Workflows API — visual approval workflows for filesystem actions.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.query_models import ApprovalRequest, WorkflowRun, WorkflowTemplate
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ── Models ────────────────────────────────────────────────────────────────────

class CreateTemplateRequest(BaseModel):
    name:          str
    description:   str = ""
    trigger_type:  str = "manual"
    trigger_config: dict[str, Any] = {}
    steps:         list[dict[str, Any]] = []


class StartRunRequest(BaseModel):
    context: dict[str, Any] = {}
    # e.g. {"files": [{"path": "smb://nas/Media/...", "name": "...", "size_bytes": ...}]}


class ApprovalDecisionRequest(BaseModel):
    decision: str   # "approved" | "rejected"
    note:     str = ""


# ── Template management ───────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List workflow templates for this tenant."""
    result = await db.execute(
        select(WorkflowTemplate).where(
            WorkflowTemplate.tenant_id == auth.tenant_id,
        ).order_by(WorkflowTemplate.name)
    )
    return [_template_to_dict(t) for t in result.scalars().all()]


@router.post("/templates")
async def create_template(
    req:  CreateTemplateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new workflow template."""
    if "actions:approve" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: actions:approve")

    template = WorkflowTemplate(
        tenant_id      = auth.tenant_id,
        created_by     = auth.user_id,
        name           = req.name,
        description    = req.description,
        trigger_type   = req.trigger_type,
        trigger_config = req.trigger_config,
        steps          = req.steps,
    )
    db.add(template)
    await db.flush()
    return _template_to_dict(template)


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return _template_to_dict(await _get_template_or_404(template_id, auth, db))


# ── Runs ──────────────────────────────────────────────────────────────────────

@router.post("/templates/{template_id}/run")
async def start_run(
    template_id: str,
    req:         StartRunRequest,
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start a workflow run from a template."""
    if "actions:propose" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: actions:propose")

    engine = WorkflowEngine(db)
    run = await engine.start_run(
        template_id      = template_id,
        tenant_id        = str(auth.tenant_id),
        context          = req.context,
        triggered_by     = "manual",
        triggered_by_user = str(auth.user_id),
    )
    return _run_to_dict(run)


@router.get("/runs")
async def list_runs(
    status: str | None = None,
    auth:   AuthContext = Depends(get_auth_context),
    db:     AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List workflow runs for this tenant."""
    stmt = select(WorkflowRun).where(WorkflowRun.tenant_id == auth.tenant_id)
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    result = await db.execute(stmt.order_by(WorkflowRun.started_at.desc()).limit(100))
    return [_run_to_dict(r) for r in result.scalars().all()]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    auth:   AuthContext = Depends(get_auth_context),
    db:     AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a workflow run with its approval requests."""
    result = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.id        == uuid.UUID(run_id),
            WorkflowRun.tenant_id == auth.tenant_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Include approval requests
    appr_result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.run_id == run.id)
        .order_by(ApprovalRequest.created_at)
    )
    approvals = appr_result.scalars().all()

    d = _run_to_dict(run)
    d["approvals"] = [_approval_to_dict(a) for a in approvals]
    return d


# ── Approvals ─────────────────────────────────────────────────────────────────

@router.get("/approvals/pending")
async def list_pending_approvals(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List approval requests pending action from the current user's tenant."""
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.tenant_id == auth.tenant_id,
            ApprovalRequest.status    == "pending",
        ).order_by(ApprovalRequest.created_at)
    )
    return [_approval_to_dict(a) for a in result.scalars().all()]


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    req:         ApprovalDecisionRequest,
    auth:        AuthContext = Depends(get_auth_context),
    db:          AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Approve or reject a pending approval request.
    Advances the workflow to the next step on approval,
    or marks it rejected on rejection.
    """
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")

    if "actions:approve" not in auth.permissions and "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Permission required: actions:approve")

    engine = WorkflowEngine(db)
    try:
        run = await engine.process_approval(
            approval_id = approval_id,
            approver_id = str(auth.user_id),
            decision    = req.decision,
            note        = req.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status":   "ok",
        "decision": req.decision,
        "run":      _run_to_dict(run),
    }


# ── Serializers ───────────────────────────────────────────────────────────────

def _template_to_dict(t: WorkflowTemplate) -> dict[str, Any]:
    return {
        "id":           str(t.id),
        "name":         t.name,
        "description":  t.description,
        "trigger_type": t.trigger_type,
        "step_count":   len(t.steps or []),
        "steps":        t.steps,
        "is_active":    t.is_active,
        "created_at":   t.created_at.isoformat() if t.created_at else None,
    }


def _run_to_dict(r: WorkflowRun) -> dict[str, Any]:
    return {
        "id":           str(r.id),
        "template_id":  str(r.template_id),
        "status":       r.status,
        "current_step": r.current_step,
        "triggered_by": r.triggered_by,
        "started_at":   r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "result":       r.result,
    }


def _approval_to_dict(a: ApprovalRequest) -> dict[str, Any]:
    return {
        "id":           str(a.id),
        "step_id":      a.step_id,
        "step_name":    a.step_name,
        "description":  a.description,
        "status":       a.status,
        "context":      a.context,
        "expires_at":   a.expires_at.isoformat() if a.expires_at else None,
        "decided_at":   a.decided_at.isoformat() if a.decided_at else None,
        "decision_note": a.decision_note,
    }


async def _get_template_or_404(
    template_id: str, auth: AuthContext, db: AsyncSession
) -> WorkflowTemplate:
    result = await db.execute(
        select(WorkflowTemplate).where(
            WorkflowTemplate.id        == uuid.UUID(template_id),
            WorkflowTemplate.tenant_id == auth.tenant_id,
        )
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return t
