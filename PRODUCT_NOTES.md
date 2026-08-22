# Product Note

## Which additional client problem I chose, and how I addressed it

I built **both** additional problems, because they reinforce each other, but the
one I invested most in is **Problem 2: Trust & Reliability** — a confidently wrong
answer is the fastest way to kill adoption of a support agent.

**Trust & Reliability.** Rather than treating retrieval as "find the most similar
text", every source is ranked by *authority* (customer agreement → current policy
→ product docs → deprecated), deprecated docs are actively demoted, and historical
tickets are labelled context-only. The agent is instructed to prefer higher
authority, and — crucially — to **surface conflicts and escalate** instead of
picking a winner when it can't safely decide. The confirmation gate means no
state change happens on the agent's say-so alone.

**Proactive Issue Detection (Problem 1).** The internal view scans tickets/orders
as of the snapshot and flags SLA breaches/near-misses (using each account's
*agreement-aware* targets), recurring complaint clusters (by category and
carrier), open P1s, and issues hitting multiple customers at once. This turns a
reactive chatbot into something that tells the team what deserves attention before
anyone asks.

## What I would build next (prioritised)

1. **Evaluation harness.** A labelled set of questions (like the two examples)
   with expected answers/decisions, run on every change. For a trust-sensitive
   product this is the highest-leverage next step. *Why: it's how you keep the
   agent from regressing as policies and data change.*
2. **Citations in the UI.** Surface the exact document + section the answer rests
   on, clickable. *Why: reviewers and customers trust what they can verify.*
3. **Grounding/faithfulness check** before replying — verify the answer's claims
   are supported by retrieved text; if not, escalate. *Why: catches hallucination
   at the last mile.*
4. **Persistent store** for sessions, actions, and an audit trail; real auth
   (SSO for staff, signed customer tokens). *Why: needed for production and for
   accountability on state changes.*
5. **Streaming responses + richer tool traces.** *Why: latency perception and
   debuggability.*
6. **Insight → action loop:** let ops turn a detected cluster into a broadcast
   status or a batch of escalations. *Why: closes the loop from detection to
   resolution.*

## What I intentionally left out

- Real authentication/RBAC infra (mocked identities per the brief).
- A vector database / embeddings (BM25 is better here for a tiny corpus).
- Real ticketing/escalation integrations (mocked to an audit log).
- Streaming and multi-tenant scaling (in-memory sessions).
- Weekend/holiday-accurate business-time math (approximated, and flagged).

## One metric I'd use to judge usefulness

**Deflection-with-trust rate:** the share of incoming requests the agent resolves
end-to-end *without* a human, **among only those it answered** — tracked
alongside its inverse guardrail, the **incorrect-answer rate** (answers later
corrected by staff). High deflection is worthless if the error rate climbs; the
product is working when deflection rises while incorrect-answers stays near zero.
A healthy escalation rate is a feature, not a failure — it's the agent correctly
recognising the limits of what it should decide.
