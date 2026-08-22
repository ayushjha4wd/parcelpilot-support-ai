# Submission Checklist (maps to the assessment form)

| Item | Status | Notes |
|---|---|---|
| **1. Repository (public)** | ⬜ push to GitHub | Commands below. README has setup + run instructions. |
| **2. Hosted application** | ⬜ deploy | `DEPLOY.md` — free HF Docker Space; set `HF_TOKEN` secret. |
| **3. Demo video (~5 min)** | ⬜ record | Script in this file (§Demo script). |
| **4. Architecture note** | ✅ | `ARCHITECTURE.md` (agent, tools, doc+data handling, reliability, trade-offs). |
| **5. Product note** | ✅ | `PRODUCT_NOTES.md` (chosen problem, next steps, omissions, metric). |
| **6. AI tool usage** | ✅ | See §AI tools below. |
| ≥3 tools, both contexts, access control, confirmation, multi-step, tool-visible UI | ✅ built & tested | |
| Both additional problems (proactive detection + trust/reliability) | ✅ | |
| **Official `ParcelPilot_Assessment_Data.xlsx`** | ✅ in place | Real workbook loaded (snapshot 2026-08-16 11:00). Loader adapted to its schema; all checks re-run and pass. |

---

## Push to GitHub

```bash
cd parcelpilot-support-ai
git init
git add .
git commit -m "ParcelPilot Support AI: dual-context agent, tools, access control, insights"
# create an EMPTY public repo on github.com first, then:
git remote add origin https://github.com/<you>/parcelpilot-support-ai.git
git branch -M main
git push -u origin main
```

## Run live locally (to test real model reasoning)

```bash
cd backend && pip install -r requirements.txt
export HF_TOKEN=hf_xxx           # your Hugging Face token
cd ../frontend && npm install && npm run build
cd ../backend && PYTHONPATH=. uvicorn app.main:app --port 8000
# open http://localhost:8000  → try the example questions below
```

## Example questions to try (real records; expected behaviour)

- *Customer = Northstar (ACCT-001):* "Can I cancel ORD-1001 without a fee?" →
  order is BOOKED, not picked up, cancel requested 120 min after booking. SOP
  would charge INR 250 (>30 min), but the Northstar agreement waives it →
  **no fee**. (Also: the closed ticket TKT-450 wrongly said INR 250 applied —
  the agent must NOT rely on that historical resolution.)
- *Customer = LumenWorks (ACCT-002):* "Am I owed a service credit on ORD-2002?"
  → pickup missed ~4.5h past the window, carrier at fault, no customer fault →
  LumenWorks agreement gives a **fixed INR 300** credit (>4h threshold met).
- *Customer = LumenWorks:* "Can I cancel ORD-2001 for free?" → cancel requested
  75 min after booking, not picked up, no waiver in their agreement → **INR 250
  fee** applies.
- *Customer = Beacon Retail (ACCT-003):* "Cancel ORD-3001 without a fee?" →
  requested within 30 min of booking → **no fee**.
- *Access:* as LumenWorks, "show me ORD-1001" → **refused** (other account).
- *Internal ops:* "What needs attention right now?" → insights flag two open
  P1s (Northstar outage TKT-501 past its 15-min SLA; Axis Labs API-key exposure
  TKT-505 past its 30-min SLA) and a recurring bulk-upload cluster.
- *Action:* internal, "escalate TKT-501" → **prepares** the escalation and asks
  to confirm before creating it.
- *Reliability trap:* "Does LumenWorks' plan cap bulk upload at 3,000 rows?"
  (TKT-451 historical answer says yes) → product guide says the limit is
  **5,000 rows**; ~3,000 is the KI-208 bug, not the policy. Agent should correct
  the historical note.

## Demo script (~5 min)

1. **Architecture** (60s): dual-context agent, one provider-agnostic LLM adapter,
   3 tool categories, access control + reliability in the tool layer.
2. **Customer flow** (90s): the ORD-1001 cancellation question — show tool chips
   (order → account → documents) and the agreement-override answer.
3. **Reliability** (45s): the deprecated-v2 vs v3 SLA question.
4. **Access control** (30s): switch to LumenWorks, try ORD-1001, get refused.
5. **Internal + confirmation** (60s): insights tab, then prepare→confirm an
   escalation.
6. **Decisions** (30s): why provider-agnostic, why BM25, why enforce in code.

## AI tools used

- **Claude (Cowork)** — designed the architecture, wrote the backend + frontend,
  built the schema-flexible loader and the source-reliability model, and created
  the deterministic mock-LLM test harness.
