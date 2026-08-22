"""The agent loop.

Responsibilities:
  - Assemble the role-scoped system prompt + tool specs.
  - Run a bounded tool-calling loop (read tools execute immediately).
  - Intercept STATE-CHANGING tool calls: instead of executing, it PREPARES the
    action and returns a `pending_action` so the UI can ask the user to confirm.
  - Emit `events` describing every tool used, so the UI can show "which tool is
    being used".

Confirmation flow:
  turn 1: user asks -> agent gathers evidence -> model calls e.g.
          create_escalation(...) -> we DO NOT run it; we return pending_action
          + an assistant message that describes it and asks to confirm.
  turn 2: user confirms -> /confirm executes the stored tool call, feeds the
          result back to the model, which writes the final confirmation.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agent.prompts import system_prompt_for
from app.auth.context import UserContext
from app.llm.adapter import llm
from app.tools.registry import registry
from app.config import settings


@dataclass
class ToolEvent:
    tool: str
    arguments: dict[str, Any]
    ok: bool
    summary: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PendingAction:
    id: str
    tool: str
    arguments: dict[str, Any]
    description: str


@dataclass
class AgentTurn:
    assistant_text: str
    events: list[ToolEvent] = field(default_factory=list)
    pending_action: PendingAction | None = None
    # Full model message list AFTER this turn (so the caller can persist it and
    # continue the conversation, including confirmation follow-ups).
    messages: list[dict[str, Any]] = field(default_factory=list)


def _short_args(args: dict[str, Any], limit: int = 200) -> str:
    s = json.dumps(args, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…"


class Agent:
    def run_turn(
        self,
        ctx: UserContext,
        history: list[dict[str, Any]],
        user_message: str,
    ) -> AgentTurn:
        messages = self._seed_messages(ctx, history, user_message)
        return self._loop(ctx, messages)

    def step(
        self,
        ctx: UserContext,
        messages: list[dict[str, Any]],
        user_message: str,
    ) -> AgentTurn:
        """Continue an ongoing conversation held as a full message list.

        Unlike run_turn, this preserves prior tool calls/results in `messages`
        (needed for the confirm flow and genuine multi-turn context). It seeds
        the system prompt exactly once.
        """
        if not messages or messages[0].get("role") != "system":
            messages = [
                {"role": "system", "content": system_prompt_for(ctx)}
            ] + list(messages)
        messages.append({"role": "user", "content": user_message})
        return self._loop(ctx, messages)

    def confirm_action(
        self,
        ctx: UserContext,
        messages: list[dict[str, Any]],
        pending: PendingAction,
        approved: bool,
    ) -> AgentTurn:
        """Execute (or decline) a previously-prepared state-changing action."""
        tool = registry.get(pending.tool)
        events: list[ToolEvent] = []

        if not approved:
            note = (
                f"The user DECLINED the prepared action '{pending.tool}'. "
                "Acknowledge that nothing was changed and ask if they want "
                "anything else."
            )
            messages.append({"role": "system", "content": note})
            return self._loop(ctx, messages, extra_events=events)

        if tool is None:
            messages.append(
                {"role": "system", "content": "Prepared tool no longer exists."}
            )
            return self._loop(ctx, messages, extra_events=events)

        # Actually execute now that the user confirmed.
        result = tool.run(ctx, **pending.arguments)
        events.append(
            ToolEvent(
                tool=pending.tool,
                arguments=pending.arguments,
                ok=result.ok,
                summary=result.message,
                meta=result.meta,
            )
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    f"The user CONFIRMED. Action '{pending.tool}' was executed. "
                    f"Result: {result.to_model_content()}. "
                    "Tell the user clearly what was done (include any reference "
                    "IDs) in one short message."
                ),
            }
        )
        return self._loop(ctx, messages, extra_events=events)

    # ------------------------------------------------------------------ #
    def _seed_messages(
        self,
        ctx: UserContext,
        history: list[dict[str, Any]],
        user_message: str,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt_for(ctx)}
        ]
        # history is a list of {role, content} (already sanitised by the API).
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _loop(
        self,
        ctx: UserContext,
        messages: list[dict[str, Any]],
        extra_events: list[ToolEvent] | None = None,
    ) -> AgentTurn:
        events: list[ToolEvent] = list(extra_events or [])
        specs = registry.specs_for(ctx)

        for _ in range(settings.max_tool_iterations):
            msg = llm.chat(messages, tools=specs, tool_choice="auto")
            tool_calls = getattr(msg, "tool_calls", None)

            # Append the assistant message (with any tool_calls) to the thread.
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_entry)

            if not tool_calls:
                return AgentTurn(
                    assistant_text=msg.content or "",
                    events=events,
                    messages=messages,
                )

            # Process each tool call.
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                tool = registry.get(name)
                if tool is None or tool not in registry.available_for(ctx):
                    # Model tried an unavailable/forbidden tool.
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {"ok": False, "message": f"Tool '{name}' is not available to you."}
                            ),
                        }
                    )
                    continue

                # STATE-CHANGING -> prepare & pause for confirmation.
                if tool.state_changing:
                    pending = PendingAction(
                        id=str(uuid.uuid4()),
                        tool=name,
                        arguments=args,
                        description=self._describe_action(name, args),
                    )
                    # Feed a note back so the model produces a confirmation ask,
                    # then stop the loop and surface the pending action.
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {
                                    "ok": True,
                                    "status": "PREPARED_AWAITING_CONFIRMATION",
                                    "message": (
                                        "Action prepared but NOT executed. Ask the "
                                        "user to confirm before it runs."
                                    ),
                                    "prepared": {"tool": name, "arguments": args},
                                }
                            ),
                        }
                    )
                    events.append(
                        ToolEvent(
                            tool=name,
                            arguments=args,
                            ok=True,
                            summary="Prepared (awaiting confirmation)",
                            meta={"prepared": True},
                        )
                    )
                    # One more model call to phrase the confirmation request.
                    followup = llm.chat(messages, tools=specs, tool_choice="none")
                    messages.append(
                        {"role": "assistant", "content": followup.content or ""}
                    )
                    return AgentTurn(
                        assistant_text=followup.content
                        or pending.description,
                        events=events,
                        pending_action=pending,
                        messages=messages,
                    )

                # READ tool -> execute now.
                result = tool.run(ctx, **args)
                events.append(
                    ToolEvent(
                        tool=name,
                        arguments=args,
                        ok=result.ok,
                        summary=result.message,
                        meta=result.meta,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.to_model_content(),
                    }
                )

        # Iteration budget exhausted.
        return AgentTurn(
            assistant_text=(
                "I wasn't able to fully resolve that within my step budget. "
                "Let me hand this to a human on the support team."
            ),
            events=events,
            messages=messages,
        )

    @staticmethod
    def _describe_action(name: str, args: dict[str, Any]) -> str:
        pretty = _short_args(args)
        return f"{name}({pretty})"


agent = Agent()
