"""Prompt grounding: inject the live state snapshot into the LLM context.

WEEK 1 SCAFFOLD: builds the grounded prompt string. The actual Ollama call and
response normalization are wired in Week 4 (TODO markers below).
"""

from __future__ import annotations

from .config import Config
from .state_engine import StateSnapshot

BASE_SYSTEM_PROMPT = (
    "You are a Linux shell. Respond ONLY with the exact terminal output of the "
    "user's command — no explanations, no markdown. Stay in character at all times."
)


def build_grounded_prompt(snapshot: StateSnapshot, config: Config) -> str:
    """Compose the system prompt fed to the LLM before each generation."""
    if not config.prompt_grounding:
        return BASE_SYSTEM_PROMPT
    return f"{BASE_SYSTEM_PROMPT}\n\n{snapshot.to_prompt_block()}"


def generate(command: str, snapshot: StateSnapshot, config: Config) -> str:
    """Generate a response for a non-deterministic command.

    TODO(week4 / SGLH-13, SGLH-14): this currently does a direct, unguarded
    call to Ollama's OpenAI-compatible endpoint. Response normalization
    (light contradiction check against `snapshot`) is NOT implemented yet —
    that's SGLH-14. Callers (see cowrie_bridge.py) must still catch
    exceptions and fall back to a safe in-character response, since this can
    raise on network errors, timeouts, or a missing/unpulled model.
    """
    import httpx

    system_prompt = build_grounded_prompt(snapshot, config)
    response = httpx.post(
        f"{config.ollama_host}/v1/chat/completions",
        json={
            "model": config.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": command},
            ],
            "stream": False,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]
