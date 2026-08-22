"""Generates a SAMPLE workbook aligned to the real policy documents so the app
can be tested end-to-end before the official ParcelPilot_Assessment_Data.xlsx
is supplied. The real workbook replaces this file (same path) with no code
changes -- the loader is schema-flexible.

Snapshot 'now' = 2026-08-21 09:00:00 (after the Aug known issues opened).
"""
import os
import pandas as pd

# NOTE: writes to a SEPARATE path so it never clobbers the official workbook at
# app/data/ParcelPilot_Assessment_Data.xlsx. To use this sample instead, set
# PARCELPILOT_WORKBOOK to the path printed below.
OUT = os.path.join(os.path.dirname(__file__), "..", "app", "data", "sample", "ParcelPilot_SAMPLE_Data.xlsx")
OUT = os.path.abspath(OUT)

SNAP = "2026-08-21 09:00:00"

readme = pd.DataFrame({
    "Field": ["Dataset", "Snapshot time (reference 'now')", "Note", "Note"],
    "Value": [
        "ParcelPilot SAMPLE assessment data (placeholder — replace with official workbook)",
        f"Dataset snapshot: {SNAP}",
        "All time-based questions use the snapshot time above as 'now'.",
        "Historical ticket resolutions may be intentionally incorrect (context only).",
    ],
})

accounts = pd.DataFrame([
    {"account_id": "ACCT-001", "name": "Northstar Logistics", "plan": "Enterprise",
     "agreement_doc_id": "northstar_agreement", "status": "ACTIVE", "csm": "Priya Mehta"},
    {"account_id": "ACCT-002", "name": "LumenWorks", "plan": "Growth",
     "agreement_doc_id": "lumenworks_agreement", "status": "ACTIVE", "csm": ""},
    {"account_id": "ACCT-003", "name": "Pinnacle Retail", "plan": "Standard",
     "agreement_doc_id": "", "status": "ACTIVE", "csm": ""},
])

# order_id, account, status, carrier, booked_at, picked_up_at, pickup window, actual pickup, fee, faults
orders = pd.DataFrame([
    # Northstar BOOKED >30min ago -> agreement waives fee
    {"order_id": "ORD-1001", "account_id": "ACCT-001", "status": "BOOKED", "carrier": "SwiftShip",
     "booked_at": "2026-08-20 10:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 09:00:00",
     "scheduled_pickup_end": "2026-08-21 11:00:00", "actual_pickup_at": "", "shipment_fee": 6000,
     "carrier_fault": "", "customer_fault": ""},
    # LumenWorks BOOKED 15 min ago -> within 30 min, no fee under SOP
    {"order_id": "ORD-1002", "account_id": "ACCT-002", "status": "BOOKED", "carrier": "QuickCarry",
     "booked_at": "2026-08-21 08:45:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 13:00:00",
     "scheduled_pickup_end": "2026-08-21 15:00:00", "actual_pickup_at": "", "shipment_fee": 2500,
     "carrier_fault": "", "customer_fault": ""},
    # Pinnacle Standard BOOKED 2h ago -> INR 250 fee (no waiver)
    {"order_id": "ORD-1003", "account_id": "ACCT-003", "status": "BOOKED", "carrier": "QuickCarry",
     "booked_at": "2026-08-21 07:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 12:00:00",
     "scheduled_pickup_end": "2026-08-21 14:00:00", "actual_pickup_at": "", "shipment_fee": 1800,
     "carrier_fault": "", "customer_fault": ""},
    # LumenWorks PICKED_UP -> cannot cancel
    {"order_id": "ORD-1004", "account_id": "ACCT-002", "status": "PICKED_UP", "carrier": "SwiftShip",
     "booked_at": "2026-08-19 09:00:00", "picked_up_at": "2026-08-20 10:00:00", "scheduled_pickup_start": "2026-08-20 09:00:00",
     "scheduled_pickup_end": "2026-08-20 11:00:00", "actual_pickup_at": "2026-08-20 10:00:00", "shipment_fee": 3200,
     "carrier_fault": "", "customer_fault": ""},
    # Northstar DELIVERED
    {"order_id": "ORD-1005", "account_id": "ACCT-001", "status": "DELIVERED", "carrier": "SwiftShip",
     "booked_at": "2026-08-15 09:00:00", "picked_up_at": "2026-08-15 12:00:00", "scheduled_pickup_start": "2026-08-15 10:00:00",
     "scheduled_pickup_end": "2026-08-15 12:00:00", "actual_pickup_at": "2026-08-15 12:00:00", "shipment_fee": 5000,
     "carrier_fault": "", "customer_fault": ""},
    # LumenWorks failed pickup 5h late, carrier fault -> eligible fixed INR 300 (agreement, >4h)
    {"order_id": "ORD-1006", "account_id": "ACCT-002", "status": "BOOKED", "carrier": "SwiftShip",
     "booked_at": "2026-08-20 20:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 02:00:00",
     "scheduled_pickup_end": "2026-08-21 04:00:00", "actual_pickup_at": "", "shipment_fee": 4000,
     "carrier_fault": "YES", "customer_fault": "NO"},
    # Northstar failed pickup 3h late, carrier fault -> default SOP >2h -> lower(500, 10%*8000=800)=500
    {"order_id": "ORD-1007", "account_id": "ACCT-001", "status": "BOOKED", "carrier": "SwiftShip",
     "booked_at": "2026-08-20 22:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 04:00:00",
     "scheduled_pickup_end": "2026-08-21 06:00:00", "actual_pickup_at": "", "shipment_fee": 8000,
     "carrier_fault": "YES", "customer_fault": "NO"},
    # Pinnacle pickup 3h late but customer fault -> not eligible
    {"order_id": "ORD-1008", "account_id": "ACCT-003", "status": "BOOKED", "carrier": "QuickCarry",
     "booked_at": "2026-08-20 23:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 04:00:00",
     "scheduled_pickup_end": "2026-08-21 06:00:00", "actual_pickup_at": "", "shipment_fee": 2000,
     "carrier_fault": "NO", "customer_fault": "YES"},
    # SwiftShip BOOKED but likely already picked up (KI-211) -> webhook delay
    {"order_id": "ORD-1009", "account_id": "ACCT-002", "status": "BOOKED", "carrier": "SwiftShip",
     "booked_at": "2026-08-21 06:00:00", "picked_up_at": "", "scheduled_pickup_start": "2026-08-21 08:30:00",
     "scheduled_pickup_end": "2026-08-21 08:45:00", "actual_pickup_at": "", "shipment_fee": 2700,
     "carrier_fault": "", "customer_fault": ""},
])

tickets = pd.DataFrame([
    # SwiftShip pickup-delay cluster (recurring issue for insights)
    {"ticket_id": "TCK-5001", "account_id": "ACCT-001", "order_id": "ORD-1007", "severity": "P2", "status": "open",
     "category": "pickup delay", "carrier": "SwiftShip", "created_at": "2026-08-21 06:30:00",
     "subject": "Pickup not collected, running late", "resolution_note": ""},
    {"ticket_id": "TCK-5002", "account_id": "ACCT-002", "order_id": "ORD-1006", "severity": "P2", "status": "open",
     "category": "pickup delay", "carrier": "SwiftShip", "created_at": "2026-08-21 05:10:00",
     "subject": "Carrier missed pickup window", "resolution_note": ""},
    {"ticket_id": "TCK-5003", "account_id": "ACCT-003", "order_id": "", "severity": "P3", "status": "open",
     "category": "pickup delay", "carrier": "SwiftShip", "created_at": "2026-08-21 07:20:00",
     "subject": "SwiftShip pickup late again", "resolution_note": ""},
    {"ticket_id": "TCK-5004", "account_id": "ACCT-002", "order_id": "ORD-1009", "severity": "P3", "status": "open",
     "category": "pickup delay", "carrier": "SwiftShip", "created_at": "2026-08-21 08:40:00",
     "subject": "Status still BOOKED but driver came?", "resolution_note": ""},
    # P1 approaching SLA (Northstar 15 min target)
    {"ticket_id": "TCK-5010", "account_id": "ACCT-001", "order_id": "", "severity": "P1", "status": "open",
     "category": "outage", "carrier": "", "created_at": "2026-08-21 08:50:00",
     "subject": "Cannot create any shipments", "resolution_note": ""},
    # P2 breached SLA (LumenWorks 4 business hours)
    {"ticket_id": "TCK-5011", "account_id": "ACCT-002", "order_id": "", "severity": "P2", "status": "open",
     "category": "feature degraded", "carrier": "", "created_at": "2026-08-21 04:00:00",
     "subject": "Label printing broken", "resolution_note": ""},
    # Bulk upload cluster (KI-208)
    {"ticket_id": "TCK-5020", "account_id": "ACCT-001", "order_id": "", "severity": "P3", "status": "open",
     "category": "bulk upload", "carrier": "", "created_at": "2026-08-20 15:00:00",
     "subject": "CSV upload fails at ~3500 rows", "resolution_note": ""},
    {"ticket_id": "TCK-5021", "account_id": "ACCT-002", "order_id": "", "severity": "P3", "status": "open",
     "category": "bulk upload", "carrier": "", "created_at": "2026-08-21 03:00:00",
     "subject": "Bulk upload errors on large file", "resolution_note": ""},
    # Ticket with INCORRECT historical resolution (must not be trusted)
    {"ticket_id": "TCK-5030", "account_id": "ACCT-003", "order_id": "ORD-1003", "severity": "P3", "status": "resolved",
     "category": "cancellation", "carrier": "", "created_at": "2026-07-10 10:00:00",
     "subject": "Cancel my booked order", "resolution_note": "Told customer BOOKED orders can always be cancelled free of charge. (NOTE: incorrect guidance)"},
])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    readme.to_excel(xw, sheet_name="README", index=False)
    accounts.to_excel(xw, sheet_name="Accounts", index=False)
    orders.to_excel(xw, sheet_name="Orders", index=False)
    tickets.to_excel(xw, sheet_name="Tickets", index=False)

print("Wrote", OUT)
print("Sheets: README, Accounts, Orders, Tickets")
print("Orders:", len(orders), "Tickets:", len(tickets), "Accounts:", len(accounts))
