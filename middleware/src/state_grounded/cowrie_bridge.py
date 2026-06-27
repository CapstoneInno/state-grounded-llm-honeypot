"""Cowrie ⇄ middleware integration bridge (SGLH-12).

Cowrie's built-in LLM backend speaks the OpenAI-compatible Chat Completions
API: it POSTs to ``{host}{path}`` (configured in ``cowrie.cfg`` as
``/v1/chat/completions``) and expects an OpenAI-shaped JSON response back.

Cowrie is run from the upstream image (no forked source), so we cannot hook
Python code directly into its process. Instead this module stands in the
place Cowrie thinks is "the LLM": Cowrie's ``host``/``path`` are pointed at
*this* server instead of Ollama. For every attacker command we:

    1. Run ``engine.try_fast_path(command)``.
       - Not ``None``  -> deterministic answer, return it, no LLM call.
       - ``None``       -> command is non-deterministic, defer to the LLM.
    2. Build the grounded system prompt from the live ``StateSnapshot``.
    3. Call ``prompt_grounding.generate()`` (forwards to Ollama).
       If that's not implemented yet (Week 4 work, SGLH-13/14) or Ollama is
       unreachable, fall back to a safe in-character response instead of
       leaking a traceback to the attacker — see docs/api/llm-backend-contract.md.

One ``StateEngine`` instance is kept per Cowrie session id so state (cwd,
files, env, $?) is tracked correctly across multiple commands in the same
attacker session, and reset when the session ends.

Run standalone:  python -m state_grounded.cowrie_bridge
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from .config import Config
from .prompt_grounding import build_grounded_prompt, generate
from .state_engine import StateEngine

logger = logging.getLogger(__name__)

# Safe, in-character fallback shown to the attacker if the LLM call fails or
# is not wired up yet. Never leak exceptions/stack traces into the session.
FALLBACK_RESPONSE = "-bash: command not found"


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
    """Identify which Cowrie session this request belongs to.

    Cowrie does not (currently) send a stable session id inside the OpenAI
    payload, so we key on a header set by the cowrie-side config docs
    recommend (X-Cowrie-Session-Id). If absent, fall back to the client's
    transport peer name so at least same-connection requests share state.
    """
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


def create_app(config: Config | None = None, registry: SessionRegistry | None = None) -> web.Application:
    """Build the aiohttp app. Exposed as a function so tests can inject state."""
    config = config or Config.from_env()
    registry = registry or SessionRegistry()

    async def chat_completions(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "invalid JSON body"}, status=400)

        command = _extract_command(payload)
        session_id = _extract_session_id(request, payload)
        engine = registry.get(session_id)
        model = payload.get("model", config.ollama_model)

        # 1. Deterministic fast-path — no LLM call at all.
        fast_result = engine.try_fast_path(command) if config.fast_path else None
        if fast_result is not None:
            logger.info("fast-path served command=%r session=%s", command, session_id)
            return web.json_response(_openai_response(fast_result, model))

        # 2. Non-deterministic — build the grounded prompt and defer to the LLM.
        snapshot = engine.snapshot()
        grounded_prompt = build_grounded_prompt(snapshot, config)
        try:
            reply = generate(command, snapshot, config)
        except NotImplementedError:
            # Week 4 grounding/generation (SGLH-13/14) not landed yet.
            logger.warning(
                "LLM generation not implemented yet; falling back. command=%r", command
            )
            reply = FALLBACK_RESPONSE
        except Exception:  # noqa: BLE001 - never leak internals to the attacker
            logger.exception("LLM call failed; falling back. command=%r", command)
            reply = FALLBACK_RESPONSE

        logger.info(
            "grounded-path served command=%r session=%s prompt_chars=%d",
            command,
            session_id,
            len(grounded_prompt),
        )
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
    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_delete("/v1/sessions/{session_id}", session_end)
    app.router.add_get("/healthz", healthz)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = Config.from_env()
    app = create_app(config)
    web.run_app(app, host="0.0.0.0", port=config.bridge_port)


if __name__ == "__main__":
    main()
