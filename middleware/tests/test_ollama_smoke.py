
from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from state_grounded import Config, StateEngine
from state_grounded.dispatch import process_command


@pytest.mark.integration
def test_fast_path_and_ollama_command() -> None:
    """
    Full-stack smoke test.

    Verifies:
    1. deterministic command -> fast-path
    2. non-deterministic command -> Ollama path
    """

    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2)
    except Exception:
        pytest.skip("Ollama is not running")

    config = Config(
        ollama_host="http://localhost:11434",
    )

    engine = StateEngine()

    reply, event = process_command(
        engine,
        "pwd",
        config,
        "smoke-session",
    )

    assert event.served_by == "fast-path"
    assert reply == "/root"

    reply, event = process_command(
        engine,
        "tell me one word",
        config,
        "smoke-session",
    )

    assert event.served_by == "llm"
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0
