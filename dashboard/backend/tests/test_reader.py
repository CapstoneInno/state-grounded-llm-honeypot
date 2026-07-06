from pathlib import Path

from dashboard.backend.app.reader import (
    get_session,
    get_sessions,
)


def test_reader(tmp_path: Path):
    log = tmp_path / "events.jsonl"

    log.write_text(
        "\n".join(
            [
                '{"session":"abc","timestamp":"2026-01-01T00:00:00Z","served_by":"fast-path"}',
                '{"session":"abc","timestamp":"2026-01-01T00:00:01Z","served_by":"llm"}',
                '{"session":"xyz","timestamp":"2026-01-01T00:00:02Z","served_by":"fast-path"}',
            ]
        ),
        encoding="utf-8",
    )

    sessions = get_sessions(log)

    assert len(sessions) == 2

    abc = next(s for s in sessions if s["session_id"] == "abc")

    assert abc["command_count"] == 2
    assert abc["llm_calls"] == 1
    assert abc["fast_path_calls"] == 1

    session = get_session("abc", log)

    assert session is not None
    assert session["session_id"] == "abc"
    assert len(session["commands"]) == 2

    assert get_session("missing", log) is None

def test_empty_log(tmp_path: Path):
    log = tmp_path / "empty.jsonl"

    log.write_text("")

    assert get_sessions(log) == []

    assert get_session("abc", log) is None
