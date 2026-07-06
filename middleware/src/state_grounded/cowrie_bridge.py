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

Also exposes admin dashboard REST API for sessions, commands, and analytics (SGLH-24..28).

Run standalone:  python -m state_grounded.cowrie_bridge
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from .config import Config
from .dispatch import process_command
from .events import EventLog
from .ingest import compute_stats, get_sessions_list, parse_events_file
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


class StreamBroadcaster:
    """Manages WebSocket connections for live event streaming."""

    def __init__(self) -> None:
        self.clients: set[web.WebSocketResponse] = set()

    async def add_client(self, ws: web.WebSocketResponse) -> None:
        self.clients.add(ws)

    async def remove_client(self, ws: web.WebSocketResponse) -> None:
        self.clients.discard(ws)

    async def broadcast(self, event: dict) -> None:
        """Send event to all connected clients."""
        message = json.dumps(event)
        dead_clients = set()
        for ws in self.clients:
            try:
                if not ws.is_closed():
                    await ws.send_str(message)
            except Exception as e:
                logger.warning("Error sending to client: %s", e)
                dead_clients.add(ws)
        self.clients -= dead_clients


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
    broadcaster = StreamBroadcaster()

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

        # Broadcast event to WebSocket clients
        await broadcaster.broadcast(
            {
                "type": "command",
                "session_id": event.session,
                "input": event.input,
                "served_by": event.served_by,
                "ts": event.timestamp,
                "exit_code": event.exit_code,
                "output": event.output,
            }
        )

        return web.json_response(_openai_response(reply, model))

    async def session_end(request: web.Request) -> web.Response:
        """Optional cleanup hook so long-running deployments don't leak memory."""
        session_id = request.match_info["session_id"]
        registry.drop(session_id)
        return web.json_response({"status": "dropped", "session_id": session_id})

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "active_sessions": len(registry)})

    # Dashboard API endpoints (SGLH-24..28)
    async def api_sessions(request: web.Request) -> web.Response:
        """GET /api/sessions — list all sessions (paginated)."""
        limit = int(request.query.get("limit", 50))
        offset = int(request.query.get("offset", 0))
        limit = min(limit, 100)  # Cap at 100

        if not config.events_log:
            return web.json_response([], status=200)

        sessions = parse_events_file(config.events_log)
        paginated = get_sessions_list(sessions, limit, offset)
        result = [s.to_dict() for s in paginated]
        return web.json_response(result, status=200)

    async def api_session_detail(request: web.Request) -> web.Response:
        """GET /api/sessions/{session_id} — full timeline for one session."""
        session_id = request.match_info["session_id"]

        if not config.events_log:
            return web.json_response(
                {"error": "events log not configured"}, status=404
            )

        sessions = parse_events_file(config.events_log)
        session = sessions.get(session_id)
        if not session:
            return web.json_response({"error": "session not found"}, status=404)

        return web.json_response(session.to_detail_dict(), status=200)

    async def api_stats(request: web.Request) -> web.Response:
        """GET /api/stats — analytics (total sessions, LLM rate, top commands)."""
        if not config.events_log:
            return web.json_response(
                {
                    "total_sessions": 0,
                    "total_commands": 0,
                    "llm_call_rate": 0.0,
                    "avg_commands_per_session": 0.0,
                    "top_commands": [],
                },
                status=200,
            )

        sessions = parse_events_file(config.events_log)
        stats = compute_stats(sessions)

        return web.json_response(stats, status=200)

    async def api_stream(request: web.Request) -> web.WebSocketResponse:
        """WS /api/stream — live event stream."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await broadcaster.add_client(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # Echo for testing; in production clients just receive
                    await ws.send_str(msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())
        finally:
            await broadcaster.remove_client(ws)

        return ws

    # CORS middleware for React frontend
    @web.middleware
    async def cors_middleware(request: web.Request, handler) -> web.Response:
        if request.method == "OPTIONS":
            return web.Response(
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )
        try:
            response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response
        except web.HTTPException as ex:
            ex.headers["Access-Control-Allow-Origin"] = "*"
            raise

    app = web.Application(middlewares=[cors_middleware])
    app["config"] = config
    app["registry"] = registry
    app["event_log"] = event_log
    app["broadcaster"] = broadcaster

    # Cowrie LLM bridge endpoints
    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_delete("/v1/sessions/{session_id}", session_end)
    app.router.add_get("/healthz", healthz)

    # Dashboard REST API endpoints
    app.router.add_get("/api/sessions", api_sessions)
    app.router.add_get("/api/sessions/{session_id}", api_session_detail)
    app.router.add_get("/api/stats", api_stats)

    # WebSocket live stream
    app.router.add_get("/api/stream", api_stream)

    return app


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(level=_log_level(config.log_level))
    app = create_app(config)
    web.run_app(app, host="0.0.0.0", port=config.bridge_port)


if __name__ == "__main__":
    main()
