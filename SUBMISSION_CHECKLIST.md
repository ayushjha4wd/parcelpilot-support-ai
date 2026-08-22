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

## Demo script — read-aloud (~5 min)

Warm the live URL first (or run locally for snappier responses). Have two
identities ready. Plain text = say it; **[SCREEN]** = do it.

**[SCREEN: login screen]**
> "Hi, I'm Ayush, and this is my submission for the ParcelPilot AI support
> assessment. It's an AI support system with two user contexts — a
> customer-facing agent and an internal operations agent — sharing one agent core
> and one set of tools. The design principle: the model decides *what* to do, but
> the guarantees — who can see what, which source to trust, and confirmation
> before an action — are enforced in code, in the tool layer, not in the prompt.
> There are seven tools across the three required categories, and a
> provider-agnostic LLM adapter that runs on Hugging Face, OpenAI, Gemini, or Groq
> via config."

**[SCREEN: Customer → Northstar → ask: Can I cancel ORD-1001 without a cancellation fee? Explain why.]**
> "As a Northstar customer, I'll ask a question that needs several steps. Watch
> the tool chips — it looks up the order and sees it's booked but not picked up,
> checks the account, then searches the documents. The standard SOP charges a
> ₹250 fee after 30 minutes, and this was cancelled two hours after booking — but
> Northstar's signed agreement waives cancellation fees entirely. Because a
> customer's own agreement outranks general policy, the answer is: no fee,
> explained from the actual sources. There's even a historical ticket in the data
> with the wrong answer here, and the agent correctly ignores it."

**[SCREEN: Switch identity → Customer → LumenWorks → ask: Show me ORD-1001]**
> "Now a different customer tries to view that same Northstar order. It's
> refused — and not by the model being polite. The data layer itself returns 'not
> authorised', because that order belongs to another account. Customers are
> hard-scoped to their own data; the model never even receives other accounts'
> records."

**[SCREEN: Switch identity → Internal staff → Ops → Insights tab]**
> "An internal ops user unlocks the proactive view. Since the real tickets have
> no severity field, it infers severity from the text and flags what needs
> attention — two open P1 incidents already past their SLA, a Northstar outage and
> a possible API-key exposure, plus a recurring bulk-upload cluster."

**[SCREEN: back to Chat → ask: Escalate TKT-501 → click Confirm]**
> "Any state-changing action is prepared first and needs explicit confirmation —
> it never acts on its own. Confirm — and it's created with a reference ID."

**[SCREEN: optional → ask: What's the Enterprise P1 first-response target?]**
> "On trust: the source pack deliberately includes a deprecated policy version and
> incorrect historical tickets. The system ranks sources by authority — agreement,
> then current policy, then product docs — demotes deprecated docs, and treats
> past ticket resolutions as untrusted context, so it won't repeat old mistakes.
>
> To close on decisions: access control and precedence live in the tool layer so
> they hold under adversarial input; the LLM adapter is provider-agnostic; and I
> used BM25 retrieval because the corpus is small and keyword-heavy. The repo has
> an architecture note, a product note, and a deterministic test harness. The next
> thing I'd add is an evaluation harness with labelled Q&A pairs. Thanks for
> watching."

## Demo script — condensed (~3 min)

**[SCREEN: login]** "I'm Ayush. This is my ParcelPilot AI support system — a
customer agent and an internal ops agent on one core. The model decides what to
do, but access control, source reliability, and confirmation before actions are
enforced in code, not the prompt. Seven tools across three categories, and a
provider-agnostic LLM layer."

**[SCREEN: Northstar → Can I cancel ORD-1001 without a cancellation fee?]** "A
multi-step question — it checks the order, the account, then the documents. The
SOP charges a fee after 30 minutes, but Northstar's agreement waives it, and the
agreement outranks policy, so: no fee, from the sources."

**[SCREEN: Switch → LumenWorks → Show me ORD-1001]** "A different customer tries
the same order — refused by the data layer, because it belongs to another
account."

**[SCREEN: Switch → Ops → Insights]** "Ops gets the proactive view — severity
inferred from text, flagging two P1s past SLA and a recurring bulk-upload
cluster."

**[SCREEN: Chat → Escalate TKT-501 → Confirm]** "State-changing actions are
prepared and need confirmation. Confirm — created with a reference ID."

**[SCREEN: close]** "Decisions: enforce in the tool layer; deprecated policy and
wrong tickets are ranked down and untrusted; provider-agnostic adapter; BM25
retrieval. Next step, an eval harness with labelled Q&A. Thanks."

## AI tools used

- **Claude (Cowork)** — designed the architecture, wrote the backend + frontend,
  built the schema-flexible workbook loader and the source-reliability model, and
  created the deterministic mock-LLM test harness. Development, git, and the
  Render deploy were driven interactively.