"""Provider-agnostic LLM adapter.

Every supported provider speaks the OpenAI chat-completions dialect, so we use
the `openai` SDK pointed at a configurable base_url. Swapping Hugging Face ->
OpenAI -> Gemini -> Groq is a config change, not a code change.

This is deliberately the *only* place that knows about the model vendor. The
agent, tools, and access-control layers are all vendor-neutral.
"""
from __future__ import annotations

from typing import Any

from openai import OpenAI

from app.config import settings


class LLMClient:
    def __init__(self) -> None:
        if not settings.api_key:
            # We don't hard-fail at import time so the app can still boot and
            # serve a clear error in the UI, but we flag it loudly.
            print(
                "[LLM] WARNING: no API key configured. Set LLM_API_KEY "
                "(or HF_TOKEN / OPENAI_API_KEY / GROQ_API_KEY / GEMINI_API_KEY)."
            )
        self._client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key or "missing-key",
            timeout=settings.request_timeout,
        )

    @property
    def model(self) -> str:
        return settings.model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> Any:
        """One round-trip. Returns the raw choice.message object.

        The caller (agent loop) inspects `.tool_calls` to decide whether to
        run tools and loop again, or to return the final text.
        """
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "temperature": settings.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message


# Singleton used across the app.
llm = LLMClient()
