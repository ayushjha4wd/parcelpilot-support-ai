# ParcelPilot Support AI

An AI support system for **ParcelPilot** (a fictional B2B logistics platform),
built for the CalQuity AI Engineer assessment. It ships **two chatbots that
share one agent + tool layer**:

- **Customer-facing agent** — answers a customer's questions scoped strictly to
  their own account (orders, cancellations, service credits, SLAs) and escalates
  when human judgment is required.
- **Internal ops agent** — lets authorised ParcelPilot staff investigate across
  accounts, act on tickets, and see a **proactive issue-detection** view
  (recurring complaints, SLA risk, P1s, multi-customer patterns).

The system reasons over an intentionally imperfect source base: policies change,
one policy version is deprecated, customer agreements override general rules, and
some historical ticket resolutions are wrong. The agent handles this with an
explicit **source-precedence / reliability model** rather than trusting every
source equally.

---

## Highlights (mapped to the assessment)

| Requirement | Where |
|---|---|
| ≥3 distinct tools (doc search / structured data / state-changing action) | `app/tools/` |
| Natural-language chat, both user contexts | `app/agent/`, `frontend/` |
| Access control in the **data/tool layer**, not the prompt | `app/auth/context.py`, enforced in every tool |
| Explicit confirmation before state-changing actions | `app/agent/agent.py` (prepare → pause → confirm) |
| Multi-step requests (order → account → agreement → policy → calc → decide) | agent loop + tool chaining |
| Interface shows which tool is used | tool-chips in `frontend/src/App.jsx` |
| Proactive issue detection (Additional Problem 1) | `app/insights/detector.py` |
| Trust & reliability (Additional Problem 2) | `app/reliability/sources.py` + demotion/precedence |
| Snapshot time as "now" | read from workbook README sheet by `app/data/loader.py` |

---

## Architecture (short version)

```
React chat UI  ──HTTP──▶  FastAPI  ──▶  Agent loop (bounded tool-calling)
                                          │
                 provider-agnostic LLM ◀──┤  (HF / OpenAI / Gemini / Groq via
                 (OpenAI-compatible)       │   one adapter — config, not code)
                                          ▼
                        ┌─────────────── Tools (each gets a trusted UserContext)
                        │  search_documents / get_document   (6 PDFs, BM25, authority-ranked)
                        │  get_account / get_order / list_* / time_between  (workbook)
                        │  detect_issues                     (internal-only insights)
                        │  create_escalation / update_ticket / create_followup_task  (state-changing)
                        └───────────────
Access control + source precedence are enforced INSIDE the tools/data layer.
```

See `ARCHITECTURE.md` and `PRODUCT_NOTES.md` for the full write-ups.

---

## Run locally

**Prereqs:** Python 3.11+, Node 20+, and an LLM API key (Hugging Face token by
default — free at <https://huggingface.co/settings/tokens>).

```bash
# 1. Backend deps
cd backend
pip install -r requirements.txt

# 2. Configure the LLM (copy and edit)
cp ../.env.example ../.env    # set HF_TOKEN=...
export $(grep -v '^#' ../.env | xargs)   # or use your own env loader

# 3. Build the frontend (outputs into backend/app/static)
cd ../frontend
npm install
npm run build

# 4. Run the server (serves API + UI)
cd ../backend
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

**Frontend dev mode** (hot reload, proxies /api to :8000):
```bash
cd frontend && npm run dev   # http://localhost:5173
```

---

## The data pack

The official workbook (`backend/app/data/ParcelPilot_Assessment_Data.xlsx`,
snapshot 2026-08-16 11:00) and the six PDFs (`backend/app/data/documents/`) are
already in place. The loader is **schema-flexible** (it maps sheets/columns by
pattern), so a revised workbook drops in without code changes. The real tickets
have no severity/category columns, so the insights engine **infers** severity and
topic from ticket text. An optional labelled sample generator lives at
`scripts/make_sample_workbook.py` (writes to `app/data/sample/`, never overwrites
the official file).

Call `POST /api/reload-data` after swapping the workbook to re-index without a
restart.

---

## Tests

```bash
cd backend
PYTHONPATH=. python tests/test_agent_mock.py    # deterministic, no API key needed
```
This exercises multi-step tool chaining, the confirm-before-act flow, and
in-loop access control using a scripted LLM.

---

## Deploy (free)

A `Dockerfile` builds the UI and serves everything from one container on port
`7860` — drop it into a **Hugging Face Docker Space** (set `HF_TOKEN` as a Space
secret), or deploy to Render/Railway. See `DEPLOY.md`.
