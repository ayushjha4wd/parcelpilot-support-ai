"""State-changing action tool(s) -- mocked but realistic.

These are the third required tool category. They are marked `state_changing`,
so the agent loop PREPARES them and waits for explicit user confirmation before
executing (see agent.py). Executions are appended to an in-memory + on-disk log
so the demo can show that actions really "happened".

In production these would call the ticketing / escalation systems. Here they
write to a JSONL audit log and return a generated reference id.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from app.auth.context import UserContext
from app.tools.registry import Tool, ToolResult, registry

_ACTION_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "action_log.jsonl")


def _log(entry: dict) -> None:
    entry = {**entry, "logged_at": datetime.now(timezone.utc).isoformat()}
    os.makedirs(os.path.dirname(_ACTION_LOG), exist_ok=True)
    with open(_ACTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


# --- create_escalation --------------------------------------------------------
def create_escalation(
    ctx: UserContext,
    reason: str,
    summary: str,
    account_id: str | None = None,
    order_id: str | None = None,
    priority: str = "normal",
) -> ToolResult:
    # Customers can only escalate for their own account.
    acct = account_id or ctx.account_id
    if ctx.is_customer and acct != ctx.account_id:
        return ToolResult(ok=False, message="You can only escalate for your own account.")
    ref = _ref("ESC")
    record = {
        "type": "escalation",
        "ref": ref,
        "account_id": acct,
        "order_id": order_id,
        "priority": priority,
        "reason": reason,
        "summary": summary,
        "raised_by": ctx.scope_label(),
    }
    _log(record)
    return ToolResult(
        ok=True,
        data=record,
        message=f"Escalation {ref} created for account {acct} (priority={priority}).",
        meta={"ref": ref},
    )


# --- update_ticket ------------------------------------------------------------
def update_ticket(
    ctx: UserContext,
    ticket_id: str,
    status: str | None = None,
    note: str | None = None,
) -> ToolResult:
    # Only internal staff may modify tickets directly.
    if not ctx.is_internal:
        return ToolResult(
            ok=False,
            message="Only ParcelPilot staff can update tickets. I can raise an escalation instead.",
        )
    record = {
        "type": "ticket_update",
        "ticket_id": ticket_id,
        "status": status,
        "note": note,
        "updated_by": ctx.scope_label(),
    }
    _log(record)
    return ToolResult(
        ok=True,
        data=record,
        message=f"Ticket {ticket_id} updated (status={status or 'unchanged'}).",
        meta={"ticket_id": ticket_id},
    )


# --- create_followup_task -----------------------------------------------------
def create_followup_task(
    ctx: UserContext,
    title: str,
    details: str,
    due: str | None = None,
    account_id: str | None = None,
) -> ToolResult:
    ref = _ref("TASK")
    record = {
        "type": "followup_task",
        "ref": ref,
        "title": title,
        "details": details,
        "due": due,
        "account_id": account_id or ctx.account_id,
        "created_by": ctx.scope_label(),
    }
    _log(record)
    return ToolResult(
        ok=True, data=record, message=f"Follow-up task {ref} created: {title}.", meta={"ref": ref}
    )


def register_action_tools() -> None:
    registry.register(
        Tool(
            name="create_escalation",
            description=(
                "Escalate an issue to the human support team. Use when a request "
                "needs human judgment, a manual exception, or an action you cannot "
                "take, or when sources conflict and you cannot safely decide."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Short reason category, e.g. 'policy conflict', 'manual exception request'."},
                    "summary": {"type": "string", "description": "What the human needs to know to act."},
                    "account_id": {"type": "string", "description": "Account the escalation relates to."},
                    "order_id": {"type": "string", "description": "Related order id, if any."},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                },
                "required": ["reason", "summary"],
            },
            handler=create_escalation,
            state_changing=True,
        )
    )
    registry.register(
        Tool(
            name="update_ticket",
            description="Update a support ticket's status and/or add an internal note. Internal staff only.",
            parameters={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "status": {"type": "string", "description": "e.g. open, in_progress, resolved, escalated."},
                    "note": {"type": "string"},
                },
                "required": ["ticket_id"],
            },
            handler=update_ticket,
            state_changing=True,
            internal_only=True,
        )
    )
    registry.register(
        Tool(
            name="create_followup_task",
            description="Create a follow-up task for the support/ops team to do later.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "due": {"type": "string", "description": "Optional due date/time (ISO)."},
                    "account_id": {"type": "string"},
                },
                "required": ["title", "details"],
            },
            handler=create_followup_task,
            state_changing=True,
        )
    )
