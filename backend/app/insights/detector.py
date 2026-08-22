"""Proactive issue detection (Additional Problem 1) -- internal only.

The real tickets sheet has NO severity/category columns, so we INFER both from
the subject/description text, then reason over them. This is closer to how a
real ops tool would work (tickets arrive as free text).

Signals surfaced (as of the dataset snapshot):
  - SLA risk: open tickets approaching or past their first-response target,
    using inferred severity and each account's agreement-aware target.
  - High severity: inferred P1s (outages, security incidents).
  - Recurring product issues: >=2 recent tickets on the same derived topic.
  - Multi-customer patterns: the same topic hitting multiple accounts.

Business-time simplification (documented): 1 business hour ~= 1 clock hour,
1 business day ~= 8h; weekends/holidays not modelled. Enough to flag for a human.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.data.loader import DATA

BUSINESS_HOUR = 60
BUSINESS_DAY = 8 * 60

PLAN_TARGETS = {
    "Enterprise": {"P1": 30, "P2": 2 * BUSINESS_HOUR, "P3": 1 * BUSINESS_DAY},
    "Growth": {"P1": 2 * BUSINESS_HOUR, "P2": 4 * BUSINESS_HOUR, "P3": 2 * BUSINESS_DAY},
    "Standard": {"P1": 4 * BUSINESS_HOUR, "P2": 1 * BUSINESS_DAY, "P3": 2 * BUSINESS_DAY},
}
# Agreement overrides keyed by account_id (from the signed agreements).
AGREEMENT_TARGETS = {
    "ACCT-001": {"P1": 15, "P2": 1 * BUSINESS_HOUR, "P3": 8 * BUSINESS_HOUR},   # Northstar
    "ACCT-002": {"P1": 2 * BUSINESS_HOUR, "P2": 4 * BUSINESS_HOUR, "P3": 2 * BUSINESS_DAY},  # LumenWorks
}


def target_minutes(account_id: str, plan: str | None, severity: str) -> int | None:
    sev = (severity or "").upper()
    if account_id in AGREEMENT_TARGETS and sev in AGREEMENT_TARGETS[account_id]:
        return AGREEMENT_TARGETS[account_id][sev]
    if plan in PLAN_TARGETS and sev in PLAN_TARGETS[plan]:
        return PLAN_TARGETS[plan][sev]
    return None


# --- text inference ----------------------------------------------------------
TOPIC_RULES = [
    ("security", r"api key|exposure|credential|security|breach|leaked|password"),
    ("outage", r"all .*fail|every .*fail|cannot create any|complete outage|http 500|is failing"),
    ("bulk upload", r"bulk upload|csv|rows"),
    ("pickup/status delay", r"pickup|picked up|booked|driver|swiftship"),
    ("cancellation", r"cancel"),
    ("billing/account", r"billing|contact|account detail|invoice"),
]

# Severity by topic (a security/outage topic is P1, etc.), overridable by cues.
TOPIC_SEVERITY = {
    "security": "P1",
    "outage": "P1",
    "bulk upload": "P2",
    "pickup/status delay": "P3",
    "cancellation": "P3",
    "billing/account": "P3",
    "other": "P3",
}


def infer_topic(text: str) -> str:
    t = text.lower()
    for topic, pat in TOPIC_RULES:
        if re.search(pat, t):
            return topic
    return "other"


def infer_severity(text: str, topic: str) -> str:
    t = text.lower()
    # Strong P1 cues regardless of topic.
    if re.search(r"api key|exposure|credential|security|breach", t):
        return "P1"
    if re.search(r"all .*fail|every .*fail|cannot create any|is failing|http 500|outage", t):
        return "P1"
    return TOPIC_SEVERITY.get(topic, "P3")


@dataclass
class Insight:
    kind: str
    severity: str
    title: str
    detail: str
    refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "title": self.title,
                "detail": self.detail, "refs": self.refs}


def _plan_for(account_id: str, accounts: pd.DataFrame) -> str | None:
    idc = DATA.col("accounts", "account_id")
    tier = DATA.col("accounts", "tier")
    if idc is None or tier is None or accounts is None:
        return None
    m = accounts[accounts[idc].astype(str) == str(account_id)]
    return None if m.empty else str(m.iloc[0][tier])


def _parse_dt(v: Any) -> datetime | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).to_pydatetime()
    try:
        return datetime.fromisoformat(str(v).replace("Z", "").replace(" ", "T"))
    except ValueError:
        return None


def _ticket_text(row, subj_col, desc_col) -> str:
    parts = []
    if subj_col and subj_col in row:
        parts.append(str(row[subj_col]))
    if desc_col and desc_col in row:
        parts.append(str(row[desc_col]))
    return " ".join(parts)


def compute_insights() -> list[Insight]:
    now = DATA.snapshot_time
    tickets = DATA.df("tickets")
    accounts = DATA.df("accounts")
    out: list[Insight] = []
    if tickets is None or now is None:
        return out

    tid = DATA.col("tickets", "ticket_id")
    acc = DATA.col("tickets", "account_id")
    stat = DATA.col("tickets", "status")
    created = DATA.col("tickets", "created_at")
    subj = DATA.col("tickets", "subject")
    desc = "description" if "description" in tickets.columns else None

    enriched = []
    for _, row in tickets.iterrows():
        text = _ticket_text(row, subj, desc)
        topic = infer_topic(text)
        sev = infer_severity(text, topic)
        enriched.append({
            "id": str(row[tid]) if tid else "?",
            "account_id": str(row[acc]) if acc else "?",
            "status": str(row[stat]).lower() if stat else "open",
            "created": _parse_dt(row[created]) if created else None,
            "topic": topic, "severity": sev, "text": text,
        })

    open_tix = [t for t in enriched if t["status"] in ("open", "in_progress")]

    # --- SLA risk (open only) --------------------------------------------
    for t in open_tix:
        plan = _plan_for(t["account_id"], accounts)
        tgt = target_minutes(t["account_id"], plan, t["severity"])
        if tgt is None or t["created"] is None:
            continue
        elapsed = (now - t["created"]).total_seconds() / 60
        if elapsed >= tgt:
            out.append(Insight("sla_risk", "critical",
                f"{t['severity']} SLA BREACHED · {t['account_id']} ({t['id']})",
                f"Open {elapsed:.0f} min vs {tgt} min target ({plan or 'plan?'}, inferred {t['severity']}). "
                f"Topic: {t['topic']}. First response overdue.",
                [t["id"]]))
        elif elapsed / tgt >= 0.7:
            out.append(Insight("sla_risk", "warning",
                f"{t['severity']} SLA approaching · {t['account_id']} ({t['id']})",
                f"Open {elapsed:.0f} of {tgt} min target ({elapsed/tgt*100:.0f}%). Topic: {t['topic']}.",
                [t["id"]]))

    # --- high severity ----------------------------------------------------
    p1 = [t for t in open_tix if t["severity"] == "P1"]
    for t in p1:
        label = "security incident" if t["topic"] == "security" else "critical outage"
        out.append(Insight("high_severity", "critical",
            f"Open P1 ({label}) · {t['account_id']} ({t['id']})",
            f"Inferred P1 from: \"{t['text'][:90]}\". Verify immediate escalation.",
            [t["id"]]))

    # --- recurring product issues (recent, any status) --------------------
    recent = [t for t in enriched if t["created"] and (now - t["created"]) <= timedelta(days=7)]
    by_topic: dict[str, list[dict]] = {}
    for t in recent:
        if t["topic"] == "other":
            continue
        by_topic.setdefault(t["topic"], []).append(t)
    for topic, group in by_topic.items():
        if len(group) >= 2:
            accts = {g["account_id"] for g in group}
            out.append(Insight("recurring", "warning",
                f"Recurring issue: {topic} ({len(group)} tickets in 7 days)",
                f"{len(group)} recent tickets on '{topic}' across {len(accts)} account(s). Possible systemic issue.",
                [g["id"] for g in group]))
            if len(accts) >= 2:
                out.append(Insight("multi_customer", "warning",
                    f"'{topic}' affecting {len(accts)} customers",
                    f"The same topic is hitting {len(accts)} different accounts. Check for a common root cause.",
                    [g["id"] for g in group]))

    order = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda i: order.get(i.severity, 3))
    return out
