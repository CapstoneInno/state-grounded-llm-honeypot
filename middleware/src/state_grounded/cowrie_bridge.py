"""Cowrie ⇄ middleware integration bridge (SGLH-12).

Cowrie's built-in LLM backend speaks the OpenAI-compatible Chat Completions
API: it POSTs to ``{host}{path}`` (configured in ``cowrie.cfg`` as
``/v1/chat/completions``) and expects an OpenAI-shaped JSON response back.

Cowrie is run from the upstream image (no forked source), so we cannot hook
Python code directly into its process. Instead this module stands in the
place Cowrie thinks is "the LLM": Cowrie's ``host``/``path`` are pointed at
*this* server instead of Ollama. For every attacker command we run
``dispatch.process_command``, which:

    1. Runs ``engine.try_fast_path(command)``.
       - Not ``None``  -> deterministic answer (served_by="fast-path").
       - ``None``       -> defer to the LLM (served_by="llm"), with a safe
         in-character fallback if generation isn't wired up / Ollama is down.
    2. Returns the reply plus a ``CommandEvent`` carrying ``served_by``.

The bridge then (a) returns the reply to Cowrie in OpenAI shape and (b) appends
the event to the middleware event log so the dashboard (SGLH-24) and tests can
see how each command was served.

One ``StateEngine`` instance is kept per Cowrie session id so state (cwd,
files, env, $?) is tracked across multiple commands in the same attacker
session, and reset when the session ends.

Run standalone:  python -m state_grounded.cowrie_bridge
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from .config import Config
from .dispatch import process_command
from .events import EventLog
from .state_engine import StateEngine

logger = logging.getLogger(__name__)


def _log_level(value: str) -> int:
    level = getattr(logging, value.upper(), logging.INFO)
    return level if isinstance(level, int) else logging.INFO


class SessionRegistry:
    """Keeps one StateEngine per Cowrie session, so state isn't shared/lost."""

    def __init__(self) -> None:
        self._engines: dict[str, StateEngine] = {}

    def get(self, session_id: str) -> StateEngine:
        engine = self._engines.get(session_id)
        if engine is None:
            engine = StateEngine()
            self._engines[session_id] = engine
        return engine

    def drop(self, session_id: str) -> None:
        self._engines.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._engines)


def _extract_command(payload: dict[str, Any]) -> str:
    """Pull the attacker's command out of an OpenAI-style chat payload.

    Cowrie sends the full running transcript as ``messages``; the command we
    need to answer is the content of the *last* ``role: user`` message.
    """
    messages = payload.get("messages") or []
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def _extract_session_id(request: web.Request, payload: dict[str, Any]) -> str:
    """Identify which Cowrie session this request belongs to."""
    header_id = request.headers.get("X-Cowrie-Session-Id")
    if header_id:
        return header_id
    model = payload.get("user") or request.remote or "default"
    return str(model)


def _openai_response(content: str, model: str) -> dict[str, Any]:
    """Wrap plain text as the OpenAI Chat Completions response Cowrie expects."""
    return {
        "id": "chatcmpl-state-grounded",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def create_app(
    config: Config | None = None,
    registry: SessionRegistry | None = None,
    event_log: EventLog | None = None,
) -> web.Application:
    """Build the aiohttp app. Exposed as a function so tests can inject state."""
    config = config or Config.from_env()
    registry = registry or SessionRegistry()
    event_log = event_log or EventLog(config.events_log)

    async def chat_completions(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "invalid JSON body"}, status=400)

        command = _extract_command(payload)
        session_id = _extract_session_id(request, payload)
        engine = registry.get(session_id)
        model = payload.get("model", config.ollama_model)

        # One place decides fast-path vs LLM and tags the event with served_by.
        reply, event = process_command(engine, command, config, session_id)
        event_log.emit(event)

        return web.json_response(_openai_response(reply, model))

    async def session_end(request: web.Request) -> web.Response:
        """Optional cleanup hook so long-running deployments don't leak memory."""
        session_id = request.match_info["session_id"]
        registry.drop(session_id)
        return web.json_response({"status": "dropped", "session_id": session_id})

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "active_sessions": len(registry)})

    app = web.Application()
    app["config"] = config
    app["registry"] = registry
    app["event_log"] = event_log
    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_delete("/v1/sessions/{session_id}", session_end)
    app.router.add_get("/healthz", healthz)
    return app


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(level=_log_level(config.log_level))
    app = create_app(config)
    web.run_app(app, host="0.0.0.0", port=config.bridge_port)


if __name__ == "__main__":
    main()
