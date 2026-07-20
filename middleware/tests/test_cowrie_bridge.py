"""Tests for the Cowrie integration bridge (SGLH-12).

Run from the middleware/ directory:  python -m pytest
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from state_grounded.config import Config  # noqa: E402
from state_grounded.cowrie_bridge import SessionRegistry, create_app  # noqa: E402


@pytest.fixture
def config() -> Config:
    # Force prompt_grounding/fast_path on; bridge_port is irrelevant for tests
    # since aiohttp's TestServer binds an ephemeral port.
    return Config()


async def _client(config: Config) -> TestClient:
    app = create_app(config=config, registry=SessionRegistry())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


def _chat_payload(command: str, session_id: str = "sess-1") -> dict:
    return {
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": command}],
        "user": session_id,
    }


@pytest.mark.asyncio
async def test_fast_path_command_served_without_llm(config: Config) -> None:
    client = await _client(config)
    try:
        resp = await client.post("/v1/chat/completions", json=_chat_payload("pwd", "s1"))
        assert resp.status == 200
        body = await resp.json()
        content = body["choices"][0]["message"]["content"]
        assert content == "/"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_state_persists_across_requests_in_same_session(config: Config) -> None:
    client = await _client(config)
    try:
        await client.post("/v1/chat/completions", json=_chat_payload("mkdir /tmp/x", "s1"))
        await client.post("/v1/chat/completions", json=_chat_payload("cd /tmp", "s1"))
        resp = await client.post("/v1/chat/completions", json=_chat_payload("ls", "s1"))
        body = await resp.json()
        content = body["choices"][0]["message"]["content"]
        assert "x" in content
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_different_sessions_do_not_share_state(config: Config) -> None:
    client = await _client(config)
    try:
        await client.post("/v1/chat/completions", json=_chat_payload("cd /tmp", "s1"))
        resp = await client.post("/v1/chat/completions", json=_chat_payload("pwd", "s2"))
        body = await resp.json()
        content = body["choices"][0]["message"]["content"]
        assert content == "/"  # s2 never cd'd, still at default cwd
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_nondeterministic_command_falls_back_safely(config: Config) -> None:
    """uname -a defers to the LLM; with no Ollama reachable in tests this
    must degrade to the safe fallback instead of raising/500ing."""
    client = await _client(config)
    try:
        resp = await client.post("/v1/chat/completions", json=_chat_payload("uname -a", "s1"))
        assert resp.status == 200
        body = await resp.json()
        assert "choices" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_healthz(config: Config) -> None:
    client = await _client(config)
    try:
        resp = await client.get("/healthz")
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "ok"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_session_end_drops_state(config: Config) -> None:
    client = await _client(config)
    try:
        await client.post("/v1/chat/completions", json=_chat_payload("cd /tmp", "s1"))
        resp = await client.delete("/v1/sessions/s1")
        assert resp.status == 200
        # After dropping, a fresh session starts back at /.
        resp2 = await client.post("/v1/chat/completions", json=_chat_payload("pwd", "s1"))
        body = await resp2.json()
        assert body["choices"][0]["message"]["content"] == "/"
    finally:
        await client.close()
