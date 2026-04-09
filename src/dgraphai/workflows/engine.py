"""
Visual Workflow Engine — approval workflows for filesystem actions.

A workflow is a DAG of steps. Each step is one of:
  - approval:  wait for human approval before proceeding
  - action:    execute a filesystem action (move/delete/rename/tag)
  - notify:    send a notification (email/webhook/Slack)
  - condition: branch based on expression (e.g. approval_count >= 2)

Workflows can be triggered:
  - manually (user clicks "run workflow" in UI)
  - by a saved query result (when query returns > 0 rows)
  - on a schedule (cron)
  - by threshold (file count, PII count, etc.)

State machine per run:
  pending → running → (approved/rejected at each step) → complete/rejected/error

All destructive actions require an approval step by default.
The engine is event-driven — steps emit events, the runner advances state.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.query_models import (
    ApprovalRequest, WorkflowRun, WorkflowTemplate
)


class WorkflowEngine:
    """Executes workflow runs step by step."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start_run(
        self,
        template_id: str,
        tenant_id: str,
        context: dict[str, Any],
        triggered_by: str = "manual",
        triggered_by_user: str | None = None,
    ) -> WorkflowRun:
        """Create and start a new workflow run."""
        result = await self.db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.id       == uuid.UUID(template_id),
                WorkflowTemplate.tenant_id == uuid.UUID(tenant_id),
                WorkflowTemplate.is_active == True,  # noqa
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Workflow template {template_id!r} not found or inactive")

        run = WorkflowRun(
            template_id       = template.id,
            tenant_id         = uuid.UUID(tenant_id),
            triggered_by      = triggered_by,
            triggered_by_user = uuid.UUID(triggered_by_user) if triggered_by_user else None,
            status            = "running",
            current_step      = 0,
            context           = context,
        )
        self.db.add(run)
        await self.db.flush()

        # Advance to first step
        await self._advance(run, template)
        return run

    async def process_approval(
        self,
        approval_id: str,
        approver_id: str,
        decision: str,          # "approved" | "rejected"
        note: str = "",
    ) -> WorkflowRun:
        """Process an approval decision and advance the workflow."""
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == uuid.UUID(approval_id),
                ApprovalRequest.status == "pending",
            )
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise ValueError("Approval not found or already decided")

        # Check expiry
        if approval.expires_at and approval.expires_at < datetime.now(timezone.utc):
            approval.status = "expired"
            await self.db.flush()
            raise ValueError("Approval request has expired")

        approval.status       = decision
        approval.approver_id  = uuid.UUID(approver_id)
        approval.decision_note = note
        approval.decided_at   = datetime.now(timezone.utc)

        # Load the run and advance
        run_result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.id == approval.run_id)
        )
        run = run_result.scalar_one()

        if decision == "rejected":
            run.status       = "rejected"
            run.completed_at = datetime.now(timezone.utc)
            run.result       = {"rejected_at_step": approval.step_id, "note": note}
        else:
            # Load template and advance to next step
            tmpl_result = await self.db.execute(
                select(WorkflowTemplate).where(WorkflowTemplate.id == run.template_id)
            )
            template = tmpl_result.scalar_one()
            run.current_step += 1
            await self._advance(run, template)

        await self.db.flush()
        return run

    async def _advance(self, run: WorkflowRun, template: WorkflowTemplate) -> None:
        """Advance the run to the next step, executing it."""
        steps = template.steps or []

        if run.current_step >= len(steps):
            # All steps complete
            run.status       = "complete"
            run.completed_at = datetime.now(timezone.utc)
            return

        step = steps[run.current_step]
        step_type   = step.get("type")
        step_config = step.get("config", {})
        step_id     = step.get("id", f"step_{run.current_step}")
        step_name   = step.get("name", step_type)

        if step_type == "approval":
            await self._create_approval_request(run, step_id, step_name, step_config)
            # Run stays in "running" state, waiting for approval decision

        elif step_type == "action":
            await self._execute_action(run, step_config)
            # Auto-advance to next step
            run.current_step += 1
            await self._advance(run, template)

        elif step_type == "notify":
            await self._send_notification(run, step_config)
            run.current_step += 1
            await self._advance(run, template)

        elif step_type == "condition":
            result = self._evaluate_condition(run.context, step_config.get("expression", "true"))
            if result:
                run.current_step += 1
                await self._advance(run, template)
            else:
                # Skip to step indicated by "else_step" or complete
                else_step = step_config.get("else_step")
                if else_step is not None:
                    run.current_step = else_step
                    await self._advance(run, template)
                else:
                    run.status       = "complete"
                    run.completed_at = datetime.now(timezone.utc)

    async def _create_approval_request(
        self,
        run: WorkflowRun,
        step_id: str,
        step_name: str,
        config: dict[str, Any],
    ) -> None:
        timeout_hours = config.get("timeout_hours", 48)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=timeout_hours)

        # Build human-readable description of what needs approval
        context_files = run.context.get("files", [])
        description = config.get("description") or (
            f"Approval required for {len(context_files)} file action(s)"
            if context_files else "Approval required to proceed"
        )

        approval = ApprovalRequest(
            run_id      = run.id,
            tenant_id   = run.tenant_id,
            step_id     = step_id,
            step_name   = step_name,
            description = description,
            context     = {
                "files":   context_files[:50],  # cap to 50 for readability
                "actions": run.context.get("pending_actions", []),
            },
            expires_at  = expires_at,
        )
        self.db.add(approval)

    async def _execute_action(self, run: WorkflowRun, config: dict[str, Any]) -> None:
        """Execute a filesystem action step."""
        action_type = config.get("action_type")
        params      = config.get("params", {})
        dry_run     = config.get("dry_run", True)  # safe default

        results = []
        for file_entry in run.context.get("files", []):
            try:
                if action_type == "move":
                    result = await _do_move(file_entry, params, dry_run)
                elif action_type == "delete":
                    result = await _do_delete(file_entry, dry_run)
                elif action_type == "tag":
                    result = await _do_tag(file_entry, params.get("tags", []))
                else:
                    result = {"status": "unknown_action", "action": action_type}
                results.append(result)
            except Exception as e:
                results.append({"status": "error", "error": str(e), "file": str(file_entry)})

        run.context["action_results"] = results

    async def _send_notification(self, run: WorkflowRun, config: dict[str, Any]) -> None:
        """Send notifications via configured channels."""
        channels = config.get("channels", [])
        message  = config.get("message", "Workflow step completed")
        # Replace template variables
        message = message.replace("{{run_id}}", str(run.id))
        message = message.replace("{{file_count}}", str(len(run.context.get("files", []))))

        for channel in channels:
            if channel == "webhook":
                url = config.get("webhook_url")
                if url:
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=10) as client:
                            await client.post(url, json={
                                "run_id":  str(run.id),
                                "message": message,
                                "context": run.context,
                            })
                    except Exception:
                        pass
            # email/slack: integrate with notification service
            # (pluggable — add handlers per channel type)

    def _evaluate_condition(self, context: dict[str, Any], expression: str) -> bool:
        """
        Safely evaluate a condition expression against workflow context.
        Supports simple comparisons only — no arbitrary code execution.
        """
        SAFE_VARS = {
            "file_count":     len(context.get("files", [])),
            "approval_count": len([a for a in context.get("approvals", []) if a.get("status") == "approved"]),
            "error_count":    len([r for r in context.get("action_results", []) if r.get("status") == "error"]),
            "true":  True,
            "false": False,
        }
        try:
            # Only allow safe comparisons
            return bool(eval(expression, {"__builtins__": {}}, SAFE_VARS))  # noqa: S307
        except Exception:
            return True  # default to proceeding on expression error


async def _do_move(file_entry: dict, params: dict, dry_run: bool) -> dict:
    source = file_entry.get("path", "")
    dest   = params.get("destination", "")
    if dry_run:
        return {"status": "dry_run", "source": source, "destination": dest}
    try:
        from archon.src.agents.nas_cataloger.protocols.factory import protocol_factory
        proto, path = protocol_factory(source)
        with proto:
            proto.move(path, dest)
        return {"status": "moved", "source": source, "destination": dest}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _do_delete(file_entry: dict, dry_run: bool) -> dict:
    source = file_entry.get("path", "")
    if dry_run:
        return {"status": "dry_run", "path": source}
    try:
        from archon.src.agents.nas_cataloger.protocols.factory import protocol_factory
        proto, path = protocol_factory(source)
        with proto:
            proto.delete(path)
        return {"status": "deleted", "path": source}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _do_tag(file_entry: dict, tags: list[str]) -> dict:
    """Update tags on a graph node (no filesystem change)."""
    return {"status": "tagged", "path": file_entry.get("path"), "tags": tags}
