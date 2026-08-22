"""Source registry + reliability/precedence model.

Every document carries metadata that lets the agent (and the retrieval tool)
reason about *authority*, not just relevance. This is the heart of the
"Trust and Reliability" problem: sources are ranked, conflicts are surfaced,
and stale/deprecated material is demoted.

Precedence (from Support Policy v3, section 1):
    1. the customer's signed agreement (for that customer only)
    2. the CURRENT general support policy / SOP
    3. CURRENT product documentation
    (historical tickets / notes are CONTEXT ONLY -- never authority)

`authority_tier`: lower number = higher authority when sources conflict.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDoc:
    doc_id: str
    title: str
    filename: str
    doc_type: str          # agreement | policy | sop | product_guide
    status: str            # current | deprecated
    authority_tier: int    # 1=agreement, 2=current policy/sop, 3=product docs, 9=deprecated
    effective: str | None = None
    account_id: str | None = None   # set for customer-specific agreements
    note: str = ""

    @property
    def is_agreement(self) -> bool:
        return self.doc_type == "agreement"

    @property
    def is_deprecated(self) -> bool:
        return self.status == "deprecated"


# The registry. Filenames match files in app/data/documents/.
SOURCES: dict[str, SourceDoc] = {
    "support_policy_v3": SourceDoc(
        doc_id="support_policy_v3",
        title="ParcelPilot Support Policy v3 (CURRENT)",
        filename="01_Support_Policy_v3_CURRENT.pdf",
        doc_type="policy",
        status="current",
        authority_tier=2,
        effective="2026-05-01",
        note="Defines default severity + first-response targets. Supersedes v2.",
    ),
    "support_policy_v2": SourceDoc(
        doc_id="support_policy_v2",
        title="ParcelPilot Support Policy v2 (DEPRECATED)",
        filename="02_Support_Policy_v2_DEPRECATED.pdf",
        doc_type="policy",
        status="deprecated",
        authority_tier=9,
        effective="2025-01-01",
        note="DEPRECATED. Retained for history only. Different SLA numbers than v3 -- must NOT be used.",
    ),
    "cancellation_sop_v4": SourceDoc(
        doc_id="cancellation_sop_v4",
        title="Cancellation & Service Credit SOP v4 (CURRENT)",
        filename="03_Cancellation_and_Service_Credit_SOP_v4.pdf",
        doc_type="sop",
        status="current",
        authority_tier=2,
        effective="2026-06-15",
        note="Cancellation fees + failed-pickup service-credit rules. Agreements may override.",
    ),
    "product_ops_guide": SourceDoc(
        doc_id="product_ops_guide",
        title="Product Operations Guide & Known Issues (CURRENT)",
        filename="04_Product_Operations_Guide_and_Known_Issues.pdf",
        doc_type="product_guide",
        status="current",
        authority_tier=3,
        effective="2026-08-14",
        note="Plan capabilities + current known issues (KI-208, KI-211). KI-176 resolved.",
    ),
    "northstar_agreement": SourceDoc(
        doc_id="northstar_agreement",
        title="Northstar Logistics Enterprise Agreement",
        filename="05_Northstar_Logistics_Enterprise_Agreement.pdf",
        doc_type="agreement",
        status="current",
        authority_tier=1,
        account_id="ACCT-001",
        note="Overrides standard SLAs; no cancellation fee on BOOKED-pre-pickup; credits capped INR 5,000/mo.",
    ),
    "lumenworks_agreement": SourceDoc(
        doc_id="lumenworks_agreement",
        title="LumenWorks Service Agreement",
        filename="06_LumenWorks_Service_Agreement.pdf",
        doc_type="agreement",
        status="current",
        authority_tier=1,
        account_id="ACCT-002",
        note="Growth plan; fixed INR 300 failed-pickup credit at >4h; no weekend support.",
    ),
}


def all_sources() -> list[SourceDoc]:
    return list(SOURCES.values())


def source_for_filename(filename: str) -> SourceDoc | None:
    for s in SOURCES.values():
        if s.filename == filename:
            return s
    return None


def visible_agreement_account(doc: SourceDoc) -> str | None:
    """For agreements, which account is allowed to see this doc (besides staff)."""
    return doc.account_id if doc.is_agreement else None


PRECEDENCE_NOTE = (
    "SOURCE PRECEDENCE when documents conflict: (1) the customer's own signed "
    "agreement, (2) the CURRENT support policy / SOP, (3) CURRENT product docs. "
    "DEPRECATED documents and historical tickets are NOT authority."
)
