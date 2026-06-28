"""CAP-11: cwd / pwd / env (PWD, HOME, USER) tracking.

Runs the harness session fixtures directly as pytest cases, so the test
suite stays in sync with the scenarios the team already defined.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from state_grounded import StateEngine  # noqa: E402

SESSIONS_DIR = Path(__file__).resolve().parents[2] / "harness" / "sessions"


def _run_session(session: dict) -> None:
    eng = StateEngine()
    for step in session["steps"]:
        cmd = step["cmd"]
        out = eng.try_fast_path(cmd)
        assert out is not None, f"{session['id']}: `{cmd}` unexpectedly deferred to LLM"

        if "expect" in step:
            assert out == step["expect"], (
                f"{session['id']}: `{cmd}` -> {out!r}, expected {step['expect']!r}"
            )
        if "expect_contains" in step:
            for fragment in step["expect_contains"]:
                assert fragment in out, (
                    f"{session['id']}: `{cmd}` -> {out!r}, expected to contain {fragment!r}"
                )


def test_cd_pwd_session_fixture() -> None:
    data = json.loads((SESSIONS_DIR / "cd-pwd-001.json").read_text())
    _run_session(data)


def test_env_basic_session_fixture() -> None:
    data = json.loads((SESSIONS_DIR / "env-basic-001.json").read_text())
    _run_session(data)


def test_fs_consistency_session_fixture() -> None:
    data = json.loads((SESSIONS_DIR / "fs-consistency-002.json").read_text())
    _run_session(data)


# --- a few extra unit tests for the individual primitives -----------------


def test_export_sets_env_var() -> None:
    eng = StateEngine()
    assert eng.try_fast_path("export FOO=bar") == ""
    assert eng.env["FOO"] == "bar"


def test_unset_removes_env_var() -> None:
    eng = StateEngine()
    eng.try_fast_path("export FOO=bar")
    eng.try_fast_path("unset FOO")
    assert "FOO" not in eng.env


def test_echo_substitutes_variables() -> None:
    eng = StateEngine()
    assert eng.try_fast_path("echo $HOME") == "/root"
    assert eng.try_fast_path("echo $NOPE") == ""


def test_cd_dotdot_navigates_up() -> None:
    eng = StateEngine()
    eng.try_fast_path("cd /var")
    eng.try_fast_path("cd ..")
    assert eng.try_fast_path("pwd") == "/"
