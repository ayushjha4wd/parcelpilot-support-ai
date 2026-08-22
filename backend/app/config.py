"""Central configuration.

The LLM layer is provider-agnostic: everything talks the OpenAI-compatible
chat-completions API. You switch providers purely with env vars, so the same
code path runs against Hugging Face's router, OpenAI, Gemini (OpenAI-compat
endpoint), Groq, or a local model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# --- Known provider presets (base_url only; you still supply the API key) ----
PROVIDER_PRESETS: dict[str, str] = {
    "huggingface": "https://router.huggingface.co/v1",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    # Gemini exposes an OpenAI-compatible surface:
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openrouter": "https://openrouter.ai/api/v1",
}

# Sensible default models per provider (all support tool/function calling).
PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "huggingface": "openai/gpt-oss-120b",          # strong open tool-caller on HF router
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openrouter": "openai/gpt-4o-mini",
}


@dataclass
class Settings:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tool_iterations: int
    request_timeout: int

    @classmethod
    def load(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "huggingface").strip().lower()
        base_url = os.getenv("LLM_BASE_URL") or PROVIDER_PRESETS.get(
            provider, PROVIDER_PRESETS["huggingface"]
        )
        # Accept a provider-specific key name or a generic one.
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("HF_TOKEN")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or ""
        )
        model = os.getenv("LLM_MODEL") or PROVIDER_DEFAULT_MODEL.get(
            provider, "openai/gpt-oss-120b"
        )
        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tool_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "8")),
            request_timeout=int(os.getenv("LLM_TIMEOUT", "60")),
        )


# Path to the candidate data pack.
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DOCS_DIR = os.path.join(DATA_DIR, "documents")
WORKBOOK_PATH = os.getenv(
    "PARCELPILOT_WORKBOOK",
    os.path.join(DATA_DIR, "ParcelPilot_Assessment_Data.xlsx"),
)

settings = Settings.load()
