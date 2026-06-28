"""Single place where a command is handled and tagged fast-path vs LLM.

Keeps the ``served_by`` decision in one testable function so the Cowrie bridge
stays thin and the tests don't need a running HTTP server.
"""

from __future__ import annotations

import logging

from .config import Config
from .events import FAST_PATH, LLM, CommandEvent
from .prompt_grounding import generate
from .state_engine import StateEngine

logger = logging.getLogger(__name__)

# Safe, in-character fallback if the LLM call fails or isn't wired up yet.
# Never leak exceptions/stack traces into the attacker session.
FALLBACK_RESPONSE = "-bash: command not found"


def process_command(
    engine: StateEngine,
    command: str,
    config: Config,
    session_id: str = "",
) -> tuple[str, CommandEvent]:
    """Handle one command and return ``(reply, event)``.

    ``event.served_by`` is ``"fast-path"`` when the deterministic engine
    answered without the LLM, or ``"llm"`` when the command was deferred to the
    model (including the fallback path when generation fails or isn't wired up).
    """
    fast_result = engine.try_fast_path(command) if config.fast_path else None

    if fast_result is not None:
        served_by = FAST_PATH
        reply = fast_result
        logger.info("fast-path served command=%r session=%s", command, session_id)
    else:
        served_by = LLM
        snapshot = engine.snapshot()
        try:
            reply = generate(command, snapshot, config)
        except NotImplementedError:
            logger.warning("LLM generation not wired yet; falling back command=%r", command)
            reply = FALLBACK_RESPONSE
        except Exception:  # noqa: BLE001 - never leak internals to the attacker
            logger.exception("LLM call failed; falling back command=%r", command)
            reply = FALLBACK_RESPONSE
        logger.info("llm served command=%r session=%s", command, session_id)

    event = CommandEvent(
        input=command,
        served_by=served_by,
        session=session_id,
        cwd=engine.cwd,
        exit_code=engine.last_exit_code,
        output=reply,
    )
    return reply, event
