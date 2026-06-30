"""Functional test suite — "does our stuff work / come up" (Stage 1).

These tests prove the project components run without errors, without requiring
Docker, Ollama, or network access.  They are broader and shallower than the
unit tests in middleware/tests/.

Usage:
    cd repo-root && python -m pytest
"""

from __future__ import annotations

import configparser
import contextlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE_SRC = REPO_ROOT / "middleware" / "src"
COWRIE_CFG = REPO_ROOT / "cowrie" / "etc" / "cowrie.cfg"
SESSIONS_DIR = REPO_ROOT / "harness" / "sessions"


@contextlib.contextmanager
def _add_src_to_path() -> None:
    saved = sys.path.copy()
    sys.path.insert(0, str(MIDDLEWARE_SRC))
    try:
        yield
    finally:
        sys.path[:] = saved


SESSIONS_SCHEMA_FIELDS = frozenset({"id", "description", "steps"})


# ---------------------------------------------------------------------------
# Group 1 — Middleware demo
# ---------------------------------------------------------------------------


def test_demo_runs_cleanly() -> None:
    """``python -m state_grounded`` exits 0, prints OK, no ERROR on stderr."""
    result = subprocess.run(
        [sys.executable, "-m", "state_grounded"],
        cwd=MIDDLEWARE_SRC,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"demo exited {result.returncode}"
    assert "Week 2 demo OK" in result.stdout, (
        f"expected success message in stdout:\n{result.stdout}"
    )
    error_lines = [line for line in result.stderr.splitlines() if "ERROR" in line]
    assert not error_lines, (
        "demo wrote ERROR to stderr:\n" + "\n".join(error_lines)
    )


# ---------------------------------------------------------------------------
# Group 2 — Cowrie config
# ---------------------------------------------------------------------------


def test_cowrie_config_is_valid_ini() -> None:
    """cowrie.cfg parses as valid INI with all required sections."""
    assert COWRIE_CFG.exists(), f"{COWRIE_CFG} not found"

    parser = configparser.ConfigParser()
    parser.read(str(COWRIE_CFG))

    assert "honeypot" in parser, "missing [honeypot] section"
    assert parser.get("honeypot", "backend") == "llm", (
        "honeypot backend must be 'llm'"
    )

    assert "llm" in parser, "missing [llm] section"
    llm_host = parser.get("llm", "host", fallback="")
    llm_path = parser.get("llm", "path", fallback="")
    assert "middleware" in llm_host, (
        f"[llm] host should point at middleware, got {llm_host!r}"
    )
    assert llm_path == "/v1/chat/completions", (
        f"[llm] path should be /v1/chat/completions, got {llm_path!r}"
    )

    assert "output_jsonlog" in parser, "missing [output_jsonlog] section"
    assert parser.getboolean("output_jsonlog", "enabled"), (
        "output_jsonlog should be enabled"
    )


# ---------------------------------------------------------------------------
# Group 3 — Harness session files
# ---------------------------------------------------------------------------


def test_harness_sessions_are_valid() -> None:
    """Every session JSON has valid structure and required fields."""
    session_files = sorted(SESSIONS_DIR.glob("*.json"))
    assert session_files, f"no session files found in {SESSIONS_DIR}"

    for path in session_files:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name}: invalid JSON — {exc}") from exc

        missing = SESSIONS_SCHEMA_FIELDS - data.keys()
        assert not missing, f"{path.name}: missing fields {missing}"

        steps = data.get("steps", [])
        assert steps, f"{path.name}: no steps"

        for i, step in enumerate(steps):
            assert step.get("cmd"), f"{path.name}: step[{i}] missing/empty 'cmd'"
            has_expect = "expect" in step or "expect_contains" in step
            assert has_expect, (
                f"{path.name}: step[{i}] needs 'expect' or 'expect_contains'"
            )


# ---------------------------------------------------------------------------
# Group 4 — Bridge starts and serves
# ---------------------------------------------------------------------------


def test_bridge_imports_and_creates_app() -> None:
    """The cowrie_bridge module can be imported and create_app works."""
    with _add_src_to_path():
        from state_grounded.cowrie_bridge import SessionRegistry, create_app  # noqa: I001
        from state_grounded.config import Config
        from state_grounded.events import EventLog

        app = create_app(
            config=Config(),
            registry=SessionRegistry(),
            event_log=EventLog(""),
        )
        assert app is not None
        methods = {r.method for r in app.router.routes()}
        assert "POST" in methods, f"expected POST route, got {methods}"
        assert "DELETE" in methods, f"expected DELETE route, got {methods}"
        assert "GET" in methods, f"expected GET route, got {methods}"


def test_bridge_dispatch_fast_path() -> None:
    """dispatch.process_command with a deterministic command returns fast-path."""
    with _add_src_to_path():
        from state_grounded import Config, StateEngine  # noqa: I001
        from state_grounded.dispatch import process_command
        from state_grounded.events import FAST_PATH

        engine = StateEngine()
        reply, event = process_command(engine, "pwd", Config(), "sess-1")
        assert event.served_by == FAST_PATH == "fast-path"
        assert reply == "/root"
        assert event.session == "sess-1"
        assert event.cwd == "/root"


def test_bridge_dispatch_unknown_command() -> None:
    """dispatch.process_command with an unknown command tags as LLM (safe fallback)."""
    with _add_src_to_path():
        from state_grounded import Config, StateEngine  # noqa: I001
        from state_grounded.dispatch import FALLBACK_RESPONSE, process_command
        from state_grounded.events import LLM

        engine = StateEngine()
        reply, event = process_command(engine, "uname -a", Config(), "sess-2")
        assert event.served_by == LLM == "llm"
        assert reply == FALLBACK_RESPONSE
        assert event.session == "sess-2"
