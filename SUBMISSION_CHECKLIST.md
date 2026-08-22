# Submission Checklist (maps to the assessment form)

**Live app:** https://parcelpilot-support-ai-eurw.onrender.com
**Repo:** https://github.com/ayushjha4wd/parcelpilot-support-ai

| Item | Status | Notes |
|---|---|---|
| **1. Repository (public)** | ✅ done | https://github.com/ayushjha4wd/parcelpilot-support-ai |
| **2. Hosted application** | ✅ done | Render (Docker, free tier): https://parcelpilot-support-ai-eurw.onrender.com |
| **3. Demo video (~5 min)** | ⬜ record | Script below (§Demo script). Loom / Drive / YouTube link. |
| **4. Architecture note** | ✅ | `ARCHITECTURE.md` (agent, tools, doc+data handling, reliability, trade-offs). |
| **5. Product note** | ✅ | `PRODUCT_NOTES.md` (chosen problem, next steps, omissions, metric). |
| **6. AI tool usage** | ✅ | See §AI tools below. |
| ≥3 tools, both contexts, access control, confirmation, multi-step, tool-visible UI | ✅ built & tested | |
| Both additional problems (proactive detection + trust/reliability) | ✅ | |
| **Official `ParcelPilot_Assessment_Data.xlsx`** | ✅ in place | Real workbook loaded (snapshot 2026-08-16 11:00). Loader adapted to its schema; all checks pass. |

> **Hosting note:** Render's free tier sleeps after ~15 min idle, so the first
> request can take ~50s to wake. Open the URL a minute before demoing/reviewing.

---

## Form field values (paste-ready)

- **GitHub Submission Link:** `https://github.com/ayushjha4wd/parcelpilot-support-ai`
- **Link to try out the Agent:** `https://parcelpilot-support-ai-eurw.onrender.com`
  (free tier — first load may take ~50s to wake)
- **Submission Video Link:** _(add after recording)_
- **Full Name / Email / LinkedIn / CV:** _(yours)_

**"Anything else you'd like us to know?"** — see the drafted blurb kept with the
submission notes (dual-context agent, access control + precedence enforced in the
tool layer, both bonus problems, provider-agnostic LLM adapter, deterministic
test harness; next step = an evaluation harness with labelled Q&A pairs).

---

## Deploy recap (Render, from GitHub)

1. render.com → **New + → Web Service** → connect the GitHub repo.
2. **Language = Docker**, **Branch = main**, **Root Directory = blank**, **Instance = Free**.
3. **Environment variable:** `HF_TOKEN` = a **write**-scoped Hugging Face token.
4. **Create Web Service** → Docker build (frontend + backend) → live `…onrender.com` URL.

To redeploy after changes: `git push` to `main`; Render auto-builds. Or in Render:
**Manual Deploy → Clear build cache & deploy** (use this if an env-var change
didn't take).

## Run live locally

```bash
cd backend && pip install -r requirements.txt
# PowerShell: $env:HF_TOKEN="hf_xxx"   |   bash: export HF_TOKEN=hf_xxx
cd ../frontend && npm install && npm run build
cd ../backend && python -m uvicorn app.main:app --port 8000
# open http://localhost:8000
```

## Tests (no API key needed)

```bash
cd backend && PYTHONPATH=. python tests/test_agent_mock.py
# multi-step chaining, confirm-before-act, in-loop access control
```

## Example questions to try (real records; expected behaviour)

- *Customer = Northstar (ACCT-001):* "Can I cancel ORD-1001 without a fee?" →
  order is BOOKED, not picked up, cancel requested 120 min after booking. SOP
  would charge INR 250 (>30 min), but the Northstar agreement waives it →
  **no fee**. (Closed ticket TKT-450 wrongly said INR 250 applied — the agent
  must NOT rely on that historical resolution.)
- *Customer = LumenWorks (ACCT-002):* "Am I owed a service credit on ORD-2002?"
  → pickup missed ~4.5h past window, carrier at fault, no customer fault →
  LumenWorks agreement gives a **fixed INR 300** credit (>4h threshold met).
- *Customer = LumenWorks:* "Can I cancel ORD-2001 for free?" → cancel requested
  75 min after booking, no waiver in their agreement → **INR 250 fee** applies.
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
  **5,000 rows**; ~3,000 is the KI-208 bug, not the policy.

## Demo script (~5 min, read-aloud)

Warm the URL first (or run locally for snappier responses). Have two identities ready.

- **0:00–0:40 Intro + architecture** — two contexts on one agent core; policy in
  the prompt, mechanism (access control, reliability, confirmation) in code;
  7 tools across 3 categories; provider-agnostic LLM adapter.
- **0:40–2:00 Customer flow** — as **Northstar**, ask *"Can I cancel ORD-1001
  without a fee?"* Show tool chips (order → account → documents); explain the
  agreement overrides the SOP fee → **no fee**, grounded in sources.
- **2:00–2:45 Access control** — Switch to **LumenWorks**, ask *"Show me
  ORD-1001"* → **refused** by the data layer, not the prompt.
- **2:45–3:45 Internal + confirmation** — **Ops → Insights** (two P1 breaches +
  bulk-upload cluster); back to Chat, *"Escalate TKT-501"* → prepares, then
  **Confirm**.
- **3:45–4:30 Trust & reliability** — ask an SLA/bulk-limit question; explain
  deprecated-v2 vs current-v3 and untrusted ticket history.
- **4:30–5:00 Key decisions + close** — enforce in code; provider-agnostic
  adapter; BM25 over embeddings; next step = eval harness with labelled Q&A.

## AI tools used

- **Claude (Cowork)** — designed the architecture, wrote the backend + frontend,
  built the schema-flexible workbook loader and the source-reliability model, and
  created the deterministic mock-LLM test harness. Development, git, and the
  Render deploy were driven interactively.