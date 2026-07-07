"""Ingest events.json (JSON-lines) into Session/Command objects (SGLH-24)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from .models import Command, Session

logger = logging.getLogger(__name__)


def parse_events_file(path: str | Path) -> dict[str, Session]:
    """Parse events.json (JSON-lines) into sessions indexed by session_id.

    Each line is a CommandEvent with:
    - input: the command
    - served_by: "fast-path" or "llm"
    - session: session ID
    - timestamp: ISO timestamp
    - exit_code: exit code
    - output: command output
    - cwd: current working directory
    """
    sessions: dict[str, Session] = defaultdict(
        lambda: Session(session_id="", src_ip="")
    )

    path = Path(path)
    if not path.exists():
        logger.warning("Events file does not exist: %s", path)
        return sessions

    try:
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                if not line.strip():
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Skipping malformed JSON on line %d: %s", line_num, e
                    )
                    continue

                session_id = event.get("session", "unknown")
                if not session_id or session_id not in sessions:
                    sessions[session_id] = Session(session_id=session_id, src_ip="")

                session = sessions[session_id]

                # Extract and populate session metadata on first event
                if not session.started_at:
                    session.started_at = event.get("timestamp", "")
                    # Try to extract src_ip from Cowrie header or event (can be in user field)
                    session.src_ip = event.get("src_ip", event.get("user", ""))

                # Update ended_at (last command timestamp)
                session.ended_at = event.get("timestamp", "")

                # Parse command
                cmd = Command(
                    ts=event.get("timestamp", ""),
                    input=event.get("input", ""),
                    output=event.get("output", ""),
                    served_by=event.get("served_by", "unknown"),
                    exit_code=event.get("exit_code", 0),
                    cwd=event.get("cwd", ""),
                )
                session.commands.append(cmd)

    except OSError as e:
        logger.error("Error reading events file %s: %s", path, e)

    return sessions


def get_sessions_list(
    sessions: dict[str, Session], limit: int = 50, offset: int = 0
) -> list[Session]:
    """Return paginated sessions sorted by most recent first."""
    # Sort by ended_at (most recent), then started_at descending
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda s: (s.ended_at or s.started_at),
        reverse=True,
    )
    return sorted_sessions[offset : offset + limit]


def compute_stats(sessions: dict[str, Session]) -> dict:
    """Compute aggregate statistics for analytics view."""
    if not sessions:
        return {
            "total_sessions": 0,
            "total_commands": 0,
            "llm_call_rate": 0.0,
            "avg_commands_per_session": 0.0,
            "top_commands": [],
        }

    total_sessions = len(sessions)
    total_commands = 0
    total_llm_calls = 0
    command_counts: dict[str, int] = defaultdict(int)

    for session in sessions.values():
        total_commands += len(session.commands)
        total_llm_calls += session.llm_calls

        for cmd in session.commands:
            # Extract base command (first word)
            parts = cmd.input.strip().split()
            if parts:
                base_cmd = parts[0]
                command_counts[base_cmd] += 1

    llm_rate = total_llm_calls / total_commands if total_commands > 0 else 0.0
    avg_cmds = total_commands / total_sessions if total_sessions > 0 else 0.0

    # Top 10 commands
    top_commands = sorted(command_counts.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]

    return {
        "total_sessions": total_sessions,
        "total_commands": total_commands,
        "llm_call_rate": llm_rate,
        "avg_commands_per_session": avg_cmds,
        "top_commands": top_commands,
    }
