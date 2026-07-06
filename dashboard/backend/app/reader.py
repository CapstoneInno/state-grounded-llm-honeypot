from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG = Path(
    os.getenv(
        "MIDDLEWARE_EVENTS_LOG",
        "var/sglh-events.jsonl",
    )
)

def load_events(path: Path = DEFAULT_LOG) -> list[dict]:
    if not path.exists():
        return []

    events: list[dict] = []

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            events.append(json.loads(line))

    return events


def get_sessions(path: Path = DEFAULT_LOG) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)

    for event in load_events(path):
        grouped[event.get("session", "")].append(event)

    sessions = []

    for session_id, events in grouped.items():
        llm_calls = sum(
            event.get("served_by") == "llm"
            for event in events
        )

        fast_path_calls = sum(
            event.get("served_by") == "fast-path"
            for event in events
        )

        sessions.append(
            {
                "session_id": session_id,
                "src_ip": "",
                "started_at": events[0]["timestamp"],
                "ended_at": events[-1]["timestamp"],
                "command_count": len(events),
                "llm_calls": llm_calls,
                "fast_path_calls": fast_path_calls,
            }
        )

    return sorted(
        sessions,
        key=lambda session: session["ended_at"],
        reverse=True,
    )


def get_session(
    session_id: str,
    path: Path = DEFAULT_LOG,
) -> dict | None:
    events = [
        event
        for event in load_events(path)
        if event.get("session") == session_id
    ]

    if not events:
        return None

    return {
        "session_id": session_id,
        "src_ip": "",
        "commands": events,
    }
