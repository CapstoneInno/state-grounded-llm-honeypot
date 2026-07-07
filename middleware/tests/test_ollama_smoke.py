
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
    2. non-deterministic *but real* command -> Ollama path

    Note: this must be a genuine shell command, not a conversational phrase.
    The SGLH-23 guard (dispatch.py::_looks_like_shell_command) now rejects
    conversational/instruction-shaped input as "command not found" before
    the LLM is ever called -- that's the point of the guard, so a phrase
    like "tell me one word" is correctly blocked, not deferred to the LLM.
    "uname -a" is real, isn't implemented by the deterministic fast-path,
    and passes the guard, so it still exercises the actual Ollama call.
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
        "uname -a",
        config,
        "smoke-session",
    )

    assert event.served_by == "llm"
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0
