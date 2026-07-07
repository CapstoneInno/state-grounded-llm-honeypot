"""Per-command event log written by the middleware (SGLH-3 · served_by).

Cowrie writes its own ``cowrie.json``, but only the middleware knows whether a
command was answered by the deterministic fast-path or deferred to the LLM. So
for every command the bridge handles we append one JSON line here, shaped like
a Cowrie command event plus a ``served_by`` field, so the admin dashboard
(SGLH-24) and the tests can see how each command was served.

``served_by`` is one of ``fast-path``, ``llm``, or ``guard`` (SGLH-23:
rejected as non-command by the deterministic prompt-injection guard before
the LLM was ever called).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# served_by values — constants so callers and tests never typo them.
FAST_PATH = "fast-path"
LLM = "llm"
GUARD = "guard"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CommandEvent:
    """One handled command, shaped like a Cowrie event plus ``served_by``."""

    input: str
    served_by: str
    session: str = ""
    cwd: str = ""
    exit_code: int = 0
    output: str = ""
    eventid: str = "sglh.command"
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventLog:
    """Append-only JSON-lines writer for :class:`CommandEvent`.

    An empty/``None`` path disables file output (events are still logged at
    DEBUG), so the middleware runs fine with no log configured and tests can
    opt in to a temp file. Writes are guarded by a lock so the async bridge can
    emit from concurrent requests safely.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or ""
        self._lock = threading.Lock()
        if self.path:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)

    def emit(self, event: CommandEvent) -> None:
        line = event.to_json()
        logger.debug("event %s", line)
        if not self.path:
            return
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
