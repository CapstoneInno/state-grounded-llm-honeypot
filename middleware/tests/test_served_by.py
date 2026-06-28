"""Tests for served_by tagging and the middleware event log (SGLH-3)."""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import state_grounded.dispatch as dispatch  # noqa: E402
from state_grounded import Config, StateEngine  # noqa: E402
from state_grounded.dispatch import process_command  # noqa: E402
from state_grounded.events import FAST_PATH, LLM, CommandEvent, EventLog  # noqa: E402


def test_deterministic_command_tagged_fast_path() -> None:
    engine = StateEngine()
    reply, event = process_command(engine, "pwd", Config(), "sess-1")
    assert event.served_by == FAST_PATH == "fast-path"
    assert event.input == "pwd"
    assert event.session == "sess-1"
    assert reply == "/root"


def test_unknown_command_tagged_llm(monkeypatch) -> None:
    # Stub the LLM call so the test is hermetic (no network).
    monkeypatch.setattr(dispatch, "generate", lambda *a, **k: "Linux svr 5.15")
    engine = StateEngine()
    reply, event = process_command(engine, "uname -a", Config(), "sess-1")
    assert event.served_by == LLM == "llm"
    assert reply == "Linux svr 5.15"


def test_llm_failure_falls_back_but_stays_tagged_llm(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("ollama unreachable")

    monkeypatch.setattr(dispatch, "generate", boom)
    engine = StateEngine()
    reply, event = process_command(engine, "uname -a", Config(), "s")
    assert event.served_by == "llm"
    assert reply == dispatch.FALLBACK_RESPONSE


def test_event_log_writes_served_by_jsonl() -> None:
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "nested", "events.jsonl")
    log = EventLog(path)
    engine = StateEngine()
    _, event = process_command(engine, "pwd", Config(), "sess-9")
    log.emit(event)
    with open(path, encoding="utf-8") as handle:
        record = json.loads(handle.readline())
    assert record["served_by"] == "fast-path"
    assert record["input"] == "pwd"
    assert record["session"] == "sess-9"
    assert record["cwd"] == "/root"
    assert "timestamp" in record


def test_event_log_disabled_is_noop() -> None:
    # Empty path must not raise and must not create files.
    EventLog("").emit(CommandEvent(input="pwd", served_by=FAST_PATH))
