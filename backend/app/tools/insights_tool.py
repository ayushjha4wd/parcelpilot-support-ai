"""Exposes proactive issue detection as an internal-only agent tool."""
from __future__ import annotations

from app.auth.context import UserContext
from app.insights.detector import compute_insights
from app.tools.registry import Tool, ToolResult, registry


def detect_issues(ctx: UserContext, kind: str | None = None) -> ToolResult:
    if not ctx.can_view_insights:
        return ToolResult(ok=False, message="Insights are available to internal ops/admin users only.")
    insights = compute_insights()
    if kind:
        insights = [i for i in insights if i.kind == kind]
    return ToolResult(
        ok=True,
        data=[i.to_dict() for i in insights],
        message=f"{len(insights)} insight(s) detected as of the dataset snapshot.",
    )


def register_insights_tool() -> None:
    registry.register(Tool(
        name="detect_issues",
        description=(
            "Scan support tickets/orders for issues that need attention: SLA "
            "breaches or approaching-SLA tickets, recurring complaint clusters, "
            "open P1/P2 incidents, and issues affecting multiple customers. "
            "Internal ops/admin only. Optional 'kind' filter: sla_risk | recurring "
            "| high_severity | multi_customer."
        ),
        parameters={"type": "object", "properties": {"kind": {"type": "string"}}},
        handler=detect_issues,
        internal_only=True,
    ))
