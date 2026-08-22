"""Tool framework.

A Tool is a callable the agent can choose. Each tool declares:
  - an OpenAI-compatible JSON schema (so the model can call it),
  - whether it is STATE-CHANGING (must be confirmed before execution),
  - whether it is INTERNAL-ONLY (hidden from customer contexts),
and receives the trusted `UserContext` on every call so it can enforce access
control itself. The model never sees tools it isn't allowed to use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.auth.context import UserContext


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    # Human/agent-readable message; this is what goes back into the model.
    message: str = ""
    # Optional structured metadata surfaced to the UI (e.g. sources used).
    meta: dict[str, Any] = field(default_factory=dict)

    def to_model_content(self) -> str:
        import json

        payload = {"ok": self.ok, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        if self.meta:
            payload["meta"] = self.meta
        return json.dumps(payload, default=str, ensure_ascii=False)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]           # JSON schema (object)
    handler: Callable[..., ToolResult]
    state_changing: bool = False
    internal_only: bool = False

    def openai_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, ctx: UserContext, **kwargs: Any) -> ToolResult:
        return self.handler(ctx, **kwargs)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def available_for(self, ctx: UserContext) -> list[Tool]:
        """Only expose tools this principal is allowed to use."""
        out = []
        for t in self._tools.values():
            if t.internal_only and not ctx.is_internal:
                continue
            out.append(t)
        return out

    def specs_for(self, ctx: UserContext) -> list[dict[str, Any]]:
        return [t.openai_spec() for t in self.available_for(ctx)]


registry = ToolRegistry()
