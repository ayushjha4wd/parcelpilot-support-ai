"""Deterministic end-to-end test of the agent loop using a scripted (mock) LLM.

Validates, with NO API key:
  - multi-step tool chaining (order -> account -> documents -> answer)
  - tool-usage events are emitted
  - access control holds inside the loop
  - state-changing actions are PREPARED and paused, then executed on confirm
"""
import json
import sys
import types

sys.path.insert(0, ".")

from app.tools import register_all_tools
register_all_tools()

from app.agent import agent as agent_mod
from app.auth.context import build_customer_context, build_internal_context, InternalRole


# ---- fake OpenAI-style message objects -------------------------------------
class FakeFn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments)

class FakeToolCall:
    def __init__(self, cid, name, arguments):
        self.id = cid
        self.function = FakeFn(name, arguments)

class FakeMsg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class ScriptedLLM:
    """Returns pre-programmed responses in order, ignoring inputs."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat(self, messages, tools=None, tool_choice="auto"):
        resp = self.script[self.calls]
        self.calls += 1
        return resp


def run_scenario(name, script, ctx, message):
    print(f"\n===== {name} =====")
    agent_mod.llm = ScriptedLLM(script)
    turn = agent_mod.agent.step(ctx, [], message)
    for e in turn.events:
        print(f"  tool -> {e.tool}({json.dumps(e.arguments)}) ok={e.ok} :: {e.summary[:70]}")
    print("  ASSISTANT:", turn.assistant_text[:200])
    if turn.pending_action:
        print("  PENDING ACTION:", turn.pending_action.tool, turn.pending_action.arguments)
    return turn


# Scenario A: customer ACCT-001 multi-step cancellation question.
scriptA = [
    FakeMsg(tool_calls=[FakeToolCall("c1", "get_order", {"order_id": "ORD-1001"})]),
    FakeMsg(tool_calls=[FakeToolCall("c2", "get_account", {"account_id": "ACCT-001"})]),
    FakeMsg(tool_calls=[FakeToolCall("c3", "search_documents", {"query": "cancellation fee BOOKED before pickup"})]),
    FakeMsg(content="ORD-1001 is BOOKED and not yet picked up. Under your Northstar Enterprise "
                    "agreement you may cancel any BOOKED shipment before pickup with no fee, which "
                    "overrides the standard INR 250 fee. So: no cancellation fee."),
]
ctxA = build_customer_context("ACCT-001")
turnA = run_scenario("A: Northstar cancel ORD-1001 (multi-step)", scriptA, ctxA, "Can I cancel ORD-1001 without a fee?")
assert [e.tool for e in turnA.events] == ["get_order", "get_account", "search_documents"], "multi-step chain failed"
assert "no" in turnA.assistant_text.lower() and "fee" in turnA.assistant_text.lower()

# Scenario B: confirmation flow for a state-changing action (internal).
scriptB = [
    FakeMsg(tool_calls=[FakeToolCall("c1", "create_escalation",
            {"reason": "policy conflict", "summary": "Customer disputes fee", "account_id": "ACCT-001", "priority": "high"})]),
    FakeMsg(content="I've prepared a HIGH-priority escalation for ACCT-001 about the disputed fee. "
                    "Shall I create it?"),
    # After confirm -> the loop calls again to write the final message:
    FakeMsg(content="Done — escalation created for ACCT-001."),
]
ctxB = build_internal_context(InternalRole.OPS)
turnB = run_scenario("B: prepare escalation (should PAUSE for confirmation)", scriptB, ctxB, "Escalate the ACCT-001 fee dispute.")
assert turnB.pending_action is not None, "should have paused for confirmation"
assert turnB.pending_action.tool == "create_escalation"

# Now confirm it.
print("\n----- confirming action -----")
turnB2 = agent_mod.agent.confirm_action(ctxB, turnB.messages, turnB.pending_action, approved=True)
for e in turnB2.events:
    print(f"  tool -> {e.tool} ok={e.ok} :: {e.summary[:80]}")
print("  ASSISTANT:", turnB2.assistant_text[:160])
assert any(e.tool == "create_escalation" and e.ok for e in turnB2.events), "escalation not executed on confirm"

# Scenario C: access control inside the loop -- customer ACCT-002 asks for ACCT-001 order.
scriptC = [
    FakeMsg(tool_calls=[FakeToolCall("c1", "get_order", {"order_id": "ORD-1001"})]),  # ORD-1001 belongs to ACCT-001
    FakeMsg(content="I'm sorry, I can't access that order — it doesn't belong to your account."),
]
ctxC = build_customer_context("ACCT-002")
turnC = run_scenario("C: LumenWorks tries Northstar order (access denied in-loop)", scriptC, ctxC, "Show me ORD-1001")
assert turnC.events[0].tool == "get_order" and turnC.events[0].ok is False, "access control did not deny"

print("\nALL MOCK ASSERTIONS PASSED ✅")
