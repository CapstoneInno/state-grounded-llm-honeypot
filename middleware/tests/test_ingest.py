"""Tests for ingest module (SGLH-24)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from state_grounded.ingest import compute_stats, get_sessions_list, parse_events_file
from state_grounded.models import Command, Session


@pytest.fixture
def sample_events_file() -> Path:
    """Create a temporary events.json with sample data."""
    events = [
        {
            "input": "pwd",
            "served_by": "fast-path",
            "session": "sess1",
            "cwd": "/root",
            "exit_code": 0,
            "output": "/root",
            "timestamp": "2026-06-14T10:00:01Z",
        },
        {
            "input": "mkdir /tmp/x",
            "served_by": "fast-path",
            "session": "sess1",
            "cwd": "/root",
            "exit_code": 0,
            "output": "",
            "timestamp": "2026-06-14T10:00:02Z",
        },
        {
            "input": "ls",
            "served_by": "llm",
            "session": "sess1",
            "cwd": "/tmp/x",
            "exit_code": 0,
            "output": "",
            "timestamp": "2026-06-14T10:00:03Z",
        },
        {
            "input": "whoami",
            "served_by": "llm",
            "session": "sess2",
            "cwd": "/root",
            "exit_code": 0,
            "output": "root",
            "timestamp": "2026-06-14T10:00:04Z",
        },
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
        return Path(f.name)


def test_parse_events_file(sample_events_file: Path) -> None:
    """Test parsing events.json into sessions."""
    sessions = parse_events_file(sample_events_file)

    assert len(sessions) == 2
    assert "sess1" in sessions
    assert "sess2" in sessions

    sess1 = sessions["sess1"]
    assert sess1.session_id == "sess1"
    assert len(sess1.commands) == 3
    assert sess1.llm_calls == 1
    assert sess1.fast_path_calls == 2

    sess2 = sessions["sess2"]
    assert sess2.session_id == "sess2"
    assert len(sess2.commands) == 1
    assert sess2.llm_calls == 1
    assert sess2.fast_path_calls == 0


def test_get_sessions_list(sample_events_file: Path) -> None:
    """Test pagination of sessions list."""
    sessions = parse_events_file(sample_events_file)
    paginated = get_sessions_list(sessions, limit=1, offset=0)

    assert len(paginated) == 1


def test_compute_stats(sample_events_file: Path) -> None:
    """Test analytics computation."""
    sessions = parse_events_file(sample_events_file)
    stats = compute_stats(sessions)

    assert stats["total_sessions"] == 2
    assert stats["total_commands"] == 4
    assert stats["llm_call_rate"] == pytest.approx(0.5)
    assert stats["avg_commands_per_session"] == pytest.approx(2.0)

    # Top commands: pwd, mkdir, ls, whoami
    assert len(stats["top_commands"]) == 4


def test_parse_empty_file() -> None:
    """Test parsing non-existent file returns empty dict."""
    sessions = parse_events_file("/tmp/nonexistent-events.json")
    assert sessions == {}


def test_malformed_json_skipped(tmp_path: Path) -> None:
    """Test that malformed JSON lines are skipped gracefully."""
    events_file = tmp_path / "events.json"
    events_file.write_text(
        '{"valid": "json"}\n'
        "not valid json\n"
        '{"another": "valid"}\n'
    )

    sessions = parse_events_file(events_file)
    # Should still parse valid lines, skip malformed
    assert len(sessions) > 0
