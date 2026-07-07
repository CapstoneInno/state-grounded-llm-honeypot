"""Tests for dashboard API endpoints (SGLH-24..28)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from state_grounded.config import Config
from state_grounded.cowrie_bridge import create_app


class TestDashboardAPI(AioHTTPTestCase):
    """Test dashboard API endpoints."""

    async def get_application(self) -> web.Application:
        """Create test app with temporary events file."""
        self.events_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )

        # Write sample events
        events = [
            {
                "input": "pwd",
                "served_by": "fast-path",
                "session": "sess1",
                "cwd": "/root",
                "exit_code": 0,
                "output": "/root",
                "timestamp": "2026-06-14T10:00:01Z",
            },
            {
                "input": "ls",
                "served_by": "llm",
                "session": "sess1",
                "cwd": "/root",
                "exit_code": 0,
                "output": "",
                "timestamp": "2026-06-14T10:00:02Z",
            },
            {
                "input": "whoami",
                "served_by": "fast-path",
                "session": "sess2",
                "cwd": "/root",
                "exit_code": 0,
                "output": "root",
                "timestamp": "2026-06-14T10:00:03Z",
            },
        ]

        for event in events:
            self.events_file.write(json.dumps(event) + "\n")
        self.events_file.flush()

        config = Config(events_log=self.events_file.name)
        return create_app(config)

    def tearDown(self) -> None:
        """Clean up temp file.

        The handle must be closed first -- on Windows, unlink() on a file
        that's still open in this process raises PermissionError (no-op on
        Linux, which is why this didn't surface until testing on Windows).
        """
        self.events_file.close()
        Path(self.events_file.name).unlink(missing_ok=True)

    @unittest_run_loop
    async def test_api_sessions(self) -> None:
        """Test GET /api/sessions endpoint."""
        resp = await self.client.request("GET", "/api/sessions")
        assert resp.status == 200

        data = await resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Check structure
        sess = data[0]
        assert "session_id" in sess
        assert "src_ip" in sess
        assert "command_count" in sess
        assert "llm_calls" in sess
        assert "fast_path_calls" in sess

    @unittest_run_loop
    async def test_api_sessions_pagination(self) -> None:
        """Test pagination parameters."""
        resp = await self.client.request("GET", "/api/sessions?limit=1&offset=0")
        assert resp.status == 200

        data = await resp.json()
        assert len(data) <= 1

    @unittest_run_loop
    async def test_api_session_detail(self) -> None:
        """Test GET /api/sessions/{session_id} endpoint."""
        resp = await self.client.request("GET", "/api/sessions/sess1")
        assert resp.status == 200

        data = await resp.json()
        assert data["session_id"] == "sess1"
        assert "commands" in data
        assert len(data["commands"]) == 2

        cmd = data["commands"][0]
        assert "ts" in cmd
        assert "input" in cmd
        assert "served_by" in cmd
        assert "exit_code" in cmd

    @unittest_run_loop
    async def test_api_session_detail_not_found(self) -> None:
        """Test session detail with non-existent ID."""
        resp = await self.client.request("GET", "/api/sessions/nonexistent")
        assert resp.status == 404

    @unittest_run_loop
    async def test_api_stats(self) -> None:
        """Test GET /api/stats endpoint."""
        resp = await self.client.request("GET", "/api/stats")
        assert resp.status == 200

        data = await resp.json()
        assert "total_sessions" in data
        assert "total_commands" in data
        assert "llm_call_rate" in data
        assert "avg_commands_per_session" in data
        assert "top_commands" in data

        assert data["total_sessions"] == 2
        assert data["total_commands"] == 3
        assert data["llm_call_rate"] == pytest.approx(1 / 3, abs=0.01)

    @unittest_run_loop
    async def test_api_stream_websocket(self) -> None:
        """Test WebSocket /api/stream endpoint."""
        async with self.client.ws_connect("/api/stream") as ws:
            assert not ws.closed
            # WebSocket should be connectable


def test_models_session_to_dict() -> None:
    """Test Session model serialization."""
    from state_grounded.models import Command, Session

    cmd1 = Command(
        ts="2026-06-14T10:00:01Z",
        input="pwd",
        output="/root",
        served_by="fast-path",
        exit_code=0,
    )
    cmd2 = Command(
        ts="2026-06-14T10:00:02Z",
        input="ls",
        output="",
        served_by="llm",
        exit_code=0,
    )

    session = Session(
        session_id="test",
        src_ip="192.168.1.1",
        started_at="2026-06-14T10:00:01Z",
        ended_at="2026-06-14T10:00:02Z",
        commands=[cmd1, cmd2],
    )

    data = session.to_dict()
    assert data["session_id"] == "test"
    assert data["command_count"] == 2
    assert data["llm_calls"] == 1
    assert data["fast_path_calls"] == 1


def test_models_session_detail_dict() -> None:
    """Test Session detail serialization."""
    from state_grounded.models import Command, Session

    cmd = Command(
        ts="2026-06-14T10:00:01Z",
        input="pwd",
        output="/root",
        served_by="fast-path",
        exit_code=0,
        cwd="/root",
    )

    session = Session(
        session_id="test",
        src_ip="192.168.1.1",
        started_at="2026-06-14T10:00:01Z",
        commands=[cmd],
    )

    data = session.to_detail_dict()
    assert data["session_id"] == "test"
    assert len(data["commands"]) == 1
    assert data["commands"][0]["input"] == "pwd"
    assert data["commands"][0]["cwd"] == "/root"
