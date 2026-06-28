"""Environment-driven configuration for the middleware.

All values come from environment variables (see ../../../.env.example) with
sensible defaults so the demo runs with zero setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Runtime configuration, loaded from the environment."""

    ollama_model: str = "qwen2.5:3b"
    ollama_host: str = "http://ollama:11434"
    fast_path: bool = True
    prompt_grounding: bool = True
    log_level: str = "INFO"
    # Port the Cowrie-integration HTTP bridge listens on (SGLH-12). Cowrie's
    # [llm] host/path in cowrie.cfg must point here instead of at Ollama
    # directly, so the middleware can intercept the command flow.
    bridge_port: int = 8090
    # Path to the per-command event log the middleware appends to (SGLH-3).
    # Each line is a JSON event with a `served_by` field ("fast-path"|"llm")
    # that the dashboard (SGLH-24) reads. Empty = file output disabled.
    events_log: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            ollama_host=os.getenv("OLLAMA_HOST", "http://ollama:11434"),
            fast_path=_as_bool(os.getenv("MIDDLEWARE_FAST_PATH"), True),
            prompt_grounding=_as_bool(os.getenv("MIDDLEWARE_PROMPT_GROUNDING"), True),
            log_level=os.getenv("MIDDLEWARE_LOG_LEVEL", "INFO"),
            bridge_port=int(os.getenv("MIDDLEWARE_BRIDGE_PORT", "8090")),
            events_log=os.getenv("MIDDLEWARE_EVENTS_LOG", ""),
        )
