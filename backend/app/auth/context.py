"""Mock authentication + access-control context.

The assessment requires access control enforced in the DATA/TOOL layer, not
in the model prompt. So every tool receives a `UserContext` and is responsible
for scoping what it returns. The prompt is *told* about the user's role, but it
is never the thing that enforces the boundary -- even if the model is tricked
into asking for another account's data, the data layer refuses.

Two user contexts:
  - CUSTOMER: tied to exactly one account_id. Can only ever see that account's
    orders/tickets and the general + their own agreement documents.
  - INTERNAL: a ParcelPilot staff member with a role (agent / ops / admin).
    Can see across accounts, scoped by role. Can run internal-only tools
    (insights, cross-account lookups).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Principal(str, Enum):
    CUSTOMER = "customer"
    INTERNAL = "internal"


class InternalRole(str, Enum):
    SUPPORT_AGENT = "support_agent"   # can view/act on tickets
    OPS = "ops"                       # + insights, cross-account investigation
    ADMIN = "admin"                   # everything


@dataclass
class UserContext:
    principal: Principal
    # For customers: the single account they belong to.
    account_id: str | None = None
    account_name: str | None = None
    # For internal users:
    role: InternalRole | None = None
    user_id: str | None = None
    display_name: str | None = None

    # ---- capability checks (used by tools & the agent) -------------------
    @property
    def is_customer(self) -> bool:
        return self.principal == Principal.CUSTOMER

    @property
    def is_internal(self) -> bool:
        return self.principal == Principal.INTERNAL

    def can_access_account(self, account_id: str) -> bool:
        """The single most important guard in the system."""
        if self.is_internal:
            return True  # internal users may investigate across accounts
        return self.account_id is not None and account_id == self.account_id

    @property
    def can_view_insights(self) -> bool:
        return self.is_internal and self.role in (
            InternalRole.OPS,
            InternalRole.ADMIN,
        )

    @property
    def can_run_actions(self) -> bool:
        # Customers can *request* actions (which become escalations); internal
        # staff can create/execute them. Both still require explicit
        # confirmation in the agent loop.
        return True

    def scope_label(self) -> str:
        if self.is_customer:
            return f"customer:{self.account_id}"
        return f"internal:{self.role.value if self.role else '?'}"


# --- Mock "session" resolution ------------------------------------------------
# In a real system these come from an auth token. Here the frontend passes a
# lightweight identity and we resolve it to a trusted server-side context.
# The account_name is backfilled from the workbook at request time so we never
# trust a client-supplied display value.

def build_customer_context(account_id: str) -> UserContext:
    return UserContext(
        principal=Principal.CUSTOMER,
        account_id=account_id,
    )


def build_internal_context(
    role: InternalRole = InternalRole.OPS,
    user_id: str = "staff-001",
    display_name: str = "ParcelPilot Staff",
) -> UserContext:
    return UserContext(
        principal=Principal.INTERNAL,
        role=role,
        user_id=user_id,
        display_name=display_name,
    )
