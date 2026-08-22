"""Structured-data lookup tool (required tool #2).

Queries the workbook (accounts / orders / tickets). Every accessor enforces
ACCESS CONTROL via UserContext: a customer only ever sees rows for their own
account; internal staff may query across accounts.

It also exposes the dataset SNAPSHOT TIME as the single source of "now" for
time-based reasoning, and a small time-delta helper so the model doesn't do
date arithmetic in its head.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.auth.context import UserContext
from app.data.loader import DATA
from app.tools.registry import Tool, ToolResult, registry


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if isinstance(v, (pd.Timestamp, datetime)):
            out[str(k)] = v.isoformat()
        elif isinstance(v, (list, tuple, dict)):
            out[str(k)] = v
        elif pd.isna(v):
            out[str(k)] = None
        elif hasattr(v, "item"):          # numpy scalar -> native python
            out[str(k)] = v.item()
        else:
            out[str(k)] = v
    return out


def _account_col(entity: str) -> str | None:
    return DATA.col(entity, "account_id")


def _filter_account(entity: str, df: pd.DataFrame, ctx: UserContext) -> pd.DataFrame:
    """Restrict a dataframe to what the user may see."""
    if ctx.is_internal:
        return df
    col = _account_col(entity)
    if col is None or ctx.account_id is None:
        # If we can't identify the account column, fail closed for customers.
        return df.iloc[0:0]
    return df[df[col].astype(str) == str(ctx.account_id)]


# ------------------------------- snapshot -----------------------------------
def get_snapshot_time(ctx: UserContext) -> ToolResult:
    if DATA.snapshot_time is None:
        return ToolResult(
            ok=False,
            message="Dataset snapshot time is not available. Treat time-based answers with caution and consider escalating.",
        )
    return ToolResult(
        ok=True,
        data={"snapshot_time": DATA.snapshot_time.isoformat(), "raw": DATA.snapshot_raw},
        message=f"Use {DATA.snapshot_time.isoformat()} as 'now' for all time-based reasoning.",
    )


# ------------------------------- accounts -----------------------------------
def get_account(ctx: UserContext, account_id: str) -> ToolResult:
    if not ctx.can_access_account(account_id):
        return ToolResult(ok=False, message="You are not authorised to view that account.")
    df = DATA.df("accounts")
    if df is None:
        return ToolResult(ok=False, message="Accounts data is unavailable.")
    idc = DATA.col("accounts", "account_id")
    match = df[df[idc].astype(str) == str(account_id)] if idc else df.iloc[0:0]
    if match.empty:
        return ToolResult(ok=True, data=None, message=f"No account found with id {account_id}.")
    return ToolResult(ok=True, data=_row_to_dict(match.iloc[0]), message=f"Account {account_id}.")


# ------------------------------- orders -------------------------------------
def get_order(ctx: UserContext, order_id: str) -> ToolResult:
    df = DATA.df("orders")
    if df is None:
        return ToolResult(ok=False, message="Orders data is unavailable.")
    idc = DATA.col("orders", "order_id")
    match = df[df[idc].astype(str) == str(order_id)] if idc else df.iloc[0:0]
    if match.empty:
        return ToolResult(ok=True, data=None, message=f"No order found with id {order_id}.")
    row = match.iloc[0]
    # Access control: the order's account must be visible to this user.
    acc_col = DATA.col("orders", "account_id")
    if acc_col is not None and ctx.is_customer:
        if str(row[acc_col]) != str(ctx.account_id):
            return ToolResult(ok=False, message="You are not authorised to view that order.")
    return ToolResult(ok=True, data=_row_to_dict(row), message=f"Order {order_id}.")


def list_orders(
    ctx: UserContext, account_id: str | None = None, status: str | None = None, limit: int = 25
) -> ToolResult:
    df = DATA.df("orders")
    if df is None:
        return ToolResult(ok=False, message="Orders data is unavailable.")
    df = _filter_account("orders", df, ctx)
    if account_id:
        if not ctx.can_access_account(account_id):
            return ToolResult(ok=False, message="You are not authorised to view that account.")
        acc_col = DATA.col("orders", "account_id")
        if acc_col:
            df = df[df[acc_col].astype(str) == str(account_id)]
    if status:
        sc = DATA.col("orders", "status")
        if sc:
            df = df[df[sc].astype(str).str.upper() == status.upper()]
    rows = [_row_to_dict(r) for _, r in df.head(limit).iterrows()]
    return ToolResult(ok=True, data=rows, message=f"{len(rows)} order(s).")


# ------------------------------- tickets ------------------------------------
def get_ticket(ctx: UserContext, ticket_id: str) -> ToolResult:
    df = DATA.df("tickets")
    if df is None:
        return ToolResult(ok=False, message="Tickets data is unavailable.")
    idc = DATA.col("tickets", "ticket_id")
    match = df[df[idc].astype(str) == str(ticket_id)] if idc else df.iloc[0:0]
    if match.empty:
        return ToolResult(ok=True, data=None, message=f"No ticket found with id {ticket_id}.")
    row = match.iloc[0]
    acc_col = DATA.col("tickets", "account_id")
    if acc_col is not None and ctx.is_customer and str(row[acc_col]) != str(ctx.account_id):
        return ToolResult(ok=False, message="You are not authorised to view that ticket.")
    data = _row_to_dict(row)
    data["_note"] = "Historical ticket content is CONTEXT ONLY and may be incorrect; do not treat it as authoritative."
    return ToolResult(ok=True, data=data, message=f"Ticket {ticket_id} (context only).")


def list_tickets(
    ctx: UserContext,
    account_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> ToolResult:
    df = DATA.df("tickets")
    if df is None:
        return ToolResult(ok=False, message="Tickets data is unavailable.")
    df = _filter_account("tickets", df, ctx)
    if account_id:
        if not ctx.can_access_account(account_id):
            return ToolResult(ok=False, message="You are not authorised to view that account.")
        acc_col = DATA.col("tickets", "account_id")
        if acc_col:
            df = df[df[acc_col].astype(str) == str(account_id)]
    if severity:
        sc = DATA.col("tickets", "severity")
        if sc:
            df = df[df[sc].astype(str).str.upper() == severity.upper()]
    if status:
        stc = DATA.col("tickets", "status")
        if stc:
            df = df[df[stc].astype(str).str.upper() == status.upper()]
    rows = [_row_to_dict(r) for _, r in df.head(limit).iterrows()]
    return ToolResult(ok=True, data=rows, message=f"{len(rows)} ticket(s) (context only).")


# ------------------------------- time helper --------------------------------
def time_between(ctx: UserContext, start_iso: str, end_iso: str | None = None) -> ToolResult:
    """Minutes/hours between two timestamps. If end omitted, uses snapshot time."""
    try:
        start = datetime.fromisoformat(str(start_iso).replace("Z", "").replace(" ", "T"))
    except ValueError:
        return ToolResult(ok=False, message=f"Could not parse start time '{start_iso}'.")
    if end_iso:
        try:
            end = datetime.fromisoformat(str(end_iso).replace("Z", "").replace(" ", "T"))
        except ValueError:
            return ToolResult(ok=False, message=f"Could not parse end time '{end_iso}'.")
    else:
        if DATA.snapshot_time is None:
            return ToolResult(ok=False, message="No end time and no dataset snapshot time available.")
        end = DATA.snapshot_time
    delta = end - start
    minutes = delta.total_seconds() / 60
    return ToolResult(
        ok=True,
        data={"minutes": round(minutes, 1), "hours": round(minutes / 60, 2),
              "start": start.isoformat(), "end": end.isoformat()},
        message=f"{round(minutes,1)} minutes ({round(minutes/60,2)} hours) between the two times.",
    )


def register_data_tools() -> None:
    registry.register(Tool(
        name="get_snapshot_time",
        description="Get the dataset snapshot time. Use this as 'now' for ANY time-based reasoning (cancellation windows, SLA breaches, pickup delays).",
        parameters={"type": "object", "properties": {}},
        handler=get_snapshot_time,
    ))
    registry.register(Tool(
        name="get_account",
        description="Look up an account by account_id (plan/tier, name, status, linked agreement).",
        parameters={"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]},
        handler=get_account,
    ))
    registry.register(Tool(
        name="get_order",
        description="Look up a single order/shipment by order_id (status, timestamps, carrier, fees, pickup window).",
        parameters={"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        handler=get_order,
    ))
    registry.register(Tool(
        name="list_orders",
        description="List orders, optionally filtered by account_id and/or status (DRAFT/BOOKED/PICKED_UP/DELIVERED).",
        parameters={"type": "object", "properties": {
            "account_id": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer"}}},
        handler=list_orders,
    ))
    registry.register(Tool(
        name="get_ticket",
        description="Look up a support ticket by ticket_id. NOTE: ticket content is context only and may be wrong.",
        parameters={"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
        handler=get_ticket,
    ))
    registry.register(Tool(
        name="list_tickets",
        description="List support tickets, optionally filtered by account_id, severity (P1/P2/P3), and/or status. Context only.",
        parameters={"type": "object", "properties": {
            "account_id": {"type": "string"}, "severity": {"type": "string"},
            "status": {"type": "string"}, "limit": {"type": "integer"}}},
        handler=list_tickets,
    ))
    registry.register(Tool(
        name="time_between",
        description="Compute minutes/hours between two ISO timestamps. If end omitted, uses the dataset snapshot time. Use this instead of doing date math yourself.",
        parameters={"type": "object", "properties": {
            "start_iso": {"type": "string"}, "end_iso": {"type": "string"}}, "required": ["start_iso"]},
        handler=time_between,
    ))
