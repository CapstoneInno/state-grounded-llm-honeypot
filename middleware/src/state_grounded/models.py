"""Data models for dashboard API (SGLH-24..28)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Command:
    """One command in a session."""

    ts: str  # ISO timestamp
    input: str
    output: str
    served_by: str  # "fast-path" or "llm"
    exit_code: int
    cwd: str = ""


@dataclass
class Session:
    """One honeypot session (attacker connection)."""

    session_id: str
    src_ip: str = ""
    started_at: str = ""  # ISO timestamp
    ended_at: str = ""  # ISO timestamp (empty if active)
    commands: list[Command] = field(default_factory=list)

    @property
    def command_count(self) -> int:
        return len(self.commands)

    @property
    def llm_calls(self) -> int:
        return sum(1 for cmd in self.commands if cmd.served_by == "llm")

    @property
    def fast_path_calls(self) -> int:
        return sum(1 for cmd in self.commands if cmd.served_by == "fast-path")

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "session_id": self.session_id,
            "src_ip": self.src_ip,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "command_count": self.command_count,
            "llm_calls": self.llm_calls,
            "fast_path_calls": self.fast_path_calls,
        }

    def to_detail_dict(self) -> dict:
        """Serialize with full command history."""
        return {
            "session_id": self.session_id,
            "src_ip": self.src_ip,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "commands": [
                {
                    "ts": cmd.ts,
                    "input": cmd.input,
                    "output": cmd.output,
                    "served_by": cmd.served_by,
                    "exit_code": cmd.exit_code,
                    "cwd": cmd.cwd,
                }
                for cmd in self.commands
            ],
        }


@dataclass
class Stats:
    """Dashboard analytics."""

    total_sessions: int
    total_commands: int
    llm_call_rate: float  # 0.0 to 1.0
    avg_commands_per_session: float
    top_commands: list[tuple[str, int]]  # (command_name, count)

    def to_dict(self) -> dict:
        return {
            "total_sessions": self.total_sessions,
            "total_commands": self.total_commands,
            "llm_call_rate": round(self.llm_call_rate, 3),
            "avg_commands_per_session": round(self.avg_commands_per_session, 2),
            "top_commands": self.top_commands,
        }
