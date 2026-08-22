# Architecture Note

## 1. Agent design

A single agent core serves **both** user contexts (customer and internal). The
context differs only in (a) the system prompt and (b) which tools are exposed —
the loop, the reliability model, and the confirmation machinery are shared.

The loop (`app/agent/agent.py`) is a bounded tool-calling cycle:

1. Assemble a role-scoped system prompt + the tool specs the user is allowed to
   call.
2. Ask the model. If it returns tool calls, run the *read* tools, append their
   results, and loop. If it returns text, that's the answer.
3. If the model calls a **state-changing** tool, the loop does **not** execute
   it. It records a `PendingAction`, asks the model to phrase a confirmation,
   and returns — the action runs only after an explicit `/api/confirm`.
4. A hard iteration cap prevents runaway loops; on exhaustion the agent hands off
   to a human rather than guessing.

This design keeps *policy* (what to do) in the prompt and *mechanism* (access
control, confirmation, evidence) in code, so the model can be wrong or adversarial
without breaking the security or safety guarantees.

## 2. Tool design

Three required categories, seven tools, each receiving a trusted `UserContext`:

- **Document search/retrieval** — `search_documents`, `get_document`. The six
  PDFs are extracted, split into section chunks, and ranked with a small,
  dependency-free **BM25** (no embedding API → fully offline, free to host).
  Every result is annotated with an **authority tier** and status so the model
  can resolve conflicts.
- **Structured-data lookup/calculation** — `get_account`, `get_order`,
  `list_orders`, `get_ticket`, `list_tickets`, plus `get_snapshot_time` and
  `time_between` so date math (cancellation windows, SLA/pickup delays) is done
  in code against the dataset snapshot, not in the model's head.
- **State-changing actions** — `create_escalation`, `update_ticket`
  (internal-only), `create_followup_task`. Mocked to a JSONL audit log; all are
  confirmation-gated.

Tools are the security boundary. The registry only advertises tools a principal
may use, and every tool re-checks access itself (defence in depth).

## 3. Access control & data privacy

`UserContext` is resolved **server-side** from an identity the client selects; the
client never supplies the account scope it can read. Enforcement lives in the
data/tool layer:

- A **customer** is bound to one `account_id`. `get_order`/`get_ticket` refuse
  records outside it; `list_*` pre-filter to it; document search hides other
  customers' agreements; `get_document` refuses another account's contract.
- An **internal** user may read across accounts; **insights** and cross-account
  actions require ops/admin.

Because the checks are in code, a prompt-injection or a confused model cannot leak
another account's data — the tool simply returns "not authorised".

## 4. Document & structured-data handling

- **Documents:** PDF → text (pdfplumber, pdftotext fallback) → section chunks →
  BM25 index, built once at startup and rebuildable via `/api/reload-data`.
- **Structured data:** the workbook is read with a **schema-flexible loader**
  that maps logical entities (accounts/orders/tickets) and fields onto whatever
  sheets/columns exist, by name pattern. The official workbook replaces the
  bundled sample with zero code changes. The **snapshot time** is parsed from the
  README sheet and is the single definition of "now".

## 5. Source reliability & conflict handling

The heart of the "trust" problem (`app/reliability/sources.py`). Each document
carries an `authority_tier`:

1. the customer's **own signed agreement** (highest),
2. the **current** support policy / SOP,
3. current **product** docs,
4. **deprecated** material (down-ranked to 0.4× in retrieval).

Historical ticket resolutions are returned with an explicit "context only, may be
incorrect" flag and are never authority. The system prompt encodes the same
precedence and instructs the agent to *surface* conflicts and escalate rather
than resolve them silently. Concretely this means: Support Policy **v2** SLAs are
ignored in favour of **v3**; Northstar's no-fee cancellation **overrides** the
INR 250 SOP fee; LumenWorks' fixed INR 300 credit at >4h **replaces** the default
INR 500/10% at >2h; and a ticket claiming "BOOKED can always be cancelled free"
is not trusted.

## 6. Major technical trade-offs

- **Provider-agnostic LLM via one OpenAI-compatible adapter.** Swapping HF ↔
  OpenAI ↔ Gemini ↔ Groq is config, not code — resilient to a provider's free
  tier running dry, and a fit for a model-agnostic infra role. Cost: we rely on
  each provider honouring the OpenAI dialect (true for all four chosen).
- **BM25 over embeddings.** The corpus is tiny and keyword-rich; BM25 is
  deterministic, instant, free, and needs no vector store or embedding calls.
  Trade-off: weaker on pure paraphrase — acceptable here, and the agent can fall
  back to `get_document`.
- **In-memory sessions.** Simple and fine for a demo; not horizontally scalable.
  A real deployment would move sessions + the audit log to a datastore.
- **Business-time approximation** in SLA insights (1 business hour ≈ 1 clock
  hour, 1 business day ≈ 8h, no weekends). Good enough to *flag* risk for a human;
  flagged explicitly as a simplification.
- **Confirmation as a loop interrupt**, not a second model. Deterministic and
  auditable; the action's exact arguments are shown before execution.
