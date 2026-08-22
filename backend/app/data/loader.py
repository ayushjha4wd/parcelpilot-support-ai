"""Loads and normalises the candidate data pack (the .xlsx workbook).

The workbook schema isn't hard-coded: we read every sheet into a DataFrame and
then map "logical entities" (accounts, orders, tickets) onto whatever sheets/
columns actually exist, via COLUMN_MAP. When you drop in the real workbook, we
confirm the sheet + column names and adjust COLUMN_MAP in one place -- nothing
else changes.

It also reads the dataset SNAPSHOT TIME from the README sheet, which the whole
system uses as "now" for time-based reasoning (per the assessment).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.config import WORKBOOK_PATH


# Logical-entity -> candidate sheet-name patterns (case-insensitive substring).
SHEET_PATTERNS = {
    "accounts": ["account", "customer", "client"],
    "orders": ["order", "shipment", "booking"],
    "tickets": ["ticket", "support", "case"],
    "readme": ["readme", "read me", "info", "meta"],
}

# Logical field -> candidate column-name patterns. Finalised against the real
# workbook. The loader picks the first matching column present in a sheet.
COLUMN_MAP = {
    "orders": {
        "order_id": ["order_id", "order id", "orderid", "id", "order"],
        "account_id": ["account_id", "account id", "accountid", "account", "customer_id"],
        "status": ["status", "state"],
        "created_at": ["created", "created_at", "order_date", "booked_at", "date"],
    },
    "accounts": {
        "account_id": ["account_id", "account id", "accountid", "id", "account"],
        "name": ["name", "account_name", "company", "customer_name"],
        "tier": ["tier", "plan", "entitlement", "contract"],
    },
    "tickets": {
        "ticket_id": ["ticket_id", "ticket id", "id", "ticket"],
        "account_id": ["account_id", "account id", "accountid", "account", "customer_id"],
        "order_id": ["order_id", "order id", "order"],
        "severity": ["severity", "priority"],
        "status": ["status", "state"],
        "created_at": ["created", "created_at", "opened_at", "date"],
        "category": ["category", "type", "topic", "issue"],
        "subject": ["subject", "title", "summary", "description"],
    },
}


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lowered = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    # substring fallback
    for cand in candidates:
        for lc, orig in lowered.items():
            if cand in lc:
                return orig
    return None


@dataclass
class DataPack:
    sheets: dict[str, pd.DataFrame] = field(default_factory=dict)
    entity_sheet: dict[str, str] = field(default_factory=dict)   # logical -> sheet name
    colmap: dict[str, dict[str, str]] = field(default_factory=dict)  # logical -> {field: real col}
    snapshot_time: datetime | None = None
    snapshot_raw: str | None = None
    loaded: bool = False
    load_error: str | None = None

    # ---- accessors ------------------------------------------------------
    def df(self, entity: str) -> pd.DataFrame | None:
        sheet = self.entity_sheet.get(entity)
        if sheet is None:
            return None
        return self.sheets.get(sheet)

    def col(self, entity: str, field_name: str) -> str | None:
        return self.colmap.get(entity, {}).get(field_name)

    def describe(self) -> dict[str, Any]:
        return {
            "loaded": self.loaded,
            "error": self.load_error,
            "sheets": {name: list(df.columns) for name, df in self.sheets.items()},
            "entity_sheet": self.entity_sheet,
            "colmap": self.colmap,
            "snapshot_time": self.snapshot_time.isoformat() if self.snapshot_time else None,
            "snapshot_raw": self.snapshot_raw,
        }


def _match_sheet(name: str, patterns: list[str]) -> bool:
    n = name.strip().lower()
    return any(p in n for p in patterns)


def _parse_snapshot(readme_df: pd.DataFrame) -> tuple[datetime | None, str | None]:
    """Look for a snapshot/reference time anywhere in the README sheet."""
    text_cells: list[str] = []
    for _, row in readme_df.iterrows():
        for val in row.tolist():
            if isinstance(val, str):
                text_cells.append(val)
            elif isinstance(val, (pd.Timestamp, datetime)):
                # A datetime cell near a "snapshot" label is our best guess.
                text_cells.append(str(val))
    joined = " \n ".join(text_cells)
    # Find an ISO-ish datetime following a snapshot/reference keyword.
    m = re.search(
        r"(snapshot|reference|as of|as-of|dataset)[^0-9]{0,40}"
        r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)",
        joined,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(2)
        try:
            return datetime.fromisoformat(raw.replace(" ", "T")), raw
        except ValueError:
            return None, raw
    # Fallback: any ISO datetime in the sheet.
    m2 = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)", joined)
    if m2:
        raw = m2.group(1)
        try:
            return datetime.fromisoformat(raw.replace(" ", "T")), raw
        except ValueError:
            return None, raw
    return None, None


def load_data_pack(path: str = WORKBOOK_PATH) -> DataPack:
    pack = DataPack()
    if not os.path.exists(path):
        pack.load_error = f"Workbook not found at {path}. Drop the data pack in to enable data tools."
        return pack
    try:
        xls = pd.read_excel(path, sheet_name=None)  # dict of all sheets
    except Exception as e:  # noqa: BLE001
        pack.load_error = f"Failed to read workbook: {e}"
        return pack

    pack.sheets = {str(k): v for k, v in xls.items()}

    # Map logical entities to sheets.
    for entity, patterns in SHEET_PATTERNS.items():
        for sheet_name in pack.sheets:
            if _match_sheet(sheet_name, patterns):
                pack.entity_sheet[entity] = sheet_name
                break

    # Map columns for each entity we found.
    for entity, fields in COLUMN_MAP.items():
        df = pack.df(entity)
        if df is None:
            continue
        pack.colmap[entity] = {}
        for logical, cands in fields.items():
            col = _find_col(df, cands)
            if col is not None:
                pack.colmap[entity][logical] = col

    # Snapshot time from README.
    readme = pack.df("readme")
    if readme is not None:
        pack.snapshot_time, pack.snapshot_raw = _parse_snapshot(readme)

    pack.loaded = True
    return pack


# Loaded once at startup; re-loadable if the file appears later.
DATA = load_data_pack()


def reload_data() -> DataPack:
    global DATA
    DATA = load_data_pack()
    return DATA
