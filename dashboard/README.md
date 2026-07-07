# Admin Dashboard (SGLH-24..28)

A real-time admin dashboard for the State-Grounded LLM Honeypot. Live monitoring of attacker sessions, commands, and whether each was served by the deterministic fast-path or the LLM.

## Features

### Sessions List (SGLH-26)
- **Real-time session overview** — all active/completed honeypot sessions
- **IP addresses** — source IP of each session
- **Command counts** — total commands, fast-path vs LLM split
- **Auto-refresh** — updates every 3 seconds + WebSocket live feed
- **Click to detail** — navigate to full command timeline

### Session Timeline (SGLH-27)
- **Per-session command history** — every command in chronological order
- **Command badge** — ⚡ Fast-Path or 🧠 LLM indicator for each
- **Exit codes** — ✓0 (success) or ✗N (error) 
- **Command output** — full output (truncated for long responses)
- **State snapshot** — cwd for each command

### Analytics (SGLH-28)
- **Aggregate metrics**
  - Total sessions & commands
  - Average commands per session
  - LLM call rate (%) vs fast-path
- **Top commands** — ranked by frequency with usage charts
- **Live data** — refreshes every 5 seconds

### Live Stream (SGLH-25)
- **WebSocket `/api/stream`** — real-time command events
- **Live indicator** — UI shows connection status
- **Auto-refresh on new commands** — sessions list updates instantly

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Browser (React SPA)                                     │
│  - SessionsList, SessionTimeline, Analytics views      │
│  - REST client + WebSocket listener                    │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP + WebSocket
                 │
┌────────────────▼────────────────────────────────────────┐
│ Backend (aiohttp, Python)                               │
│  - /api/sessions          → list all sessions          │
│  - /api/sessions/{id}     → full command timeline      │
│  - /api/stats             → analytics                  │
│  - /api/stream (WebSocket) → live events              │
│  - /v1/chat/completions   → Cowrie LLM bridge         │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ reads
                 ▼
         events.json (JSON-lines)
         - CommandEvent per line
         - served_by: fast-path | llm
```

## API Endpoints

### `GET /api/sessions?limit=50&offset=0`
List sessions (most recent first).

```json
[
  {
    "session_id": "a1b2c3",
    "src_ip": "203.0.113.7",
    "started_at": "2026-06-14T10:00:01Z",
    "ended_at": "2026-06-14T10:03:12Z",
    "command_count": 14,
    "llm_calls": 5,
    "fast_path_calls": 9
  }
]
```

### `GET /api/sessions/{session_id}`
Full command timeline for one session.

```json
{
  "session_id": "a1b2c3",
  "src_ip": "203.0.113.7",
  "started_at": "2026-06-14T10:00:01Z",
  "ended_at": "2026-06-14T10:03:12Z",
  "commands": [
    {
      "ts": "2026-06-14T10:00:05Z",
      "input": "mkdir /tmp/x",
      "output": "",
      "served_by": "fast-path",
      "exit_code": 0,
      "cwd": "/root"
    },
    {
      "ts": "2026-06-14T10:00:09Z",
      "input": "uname -a",
      "output": "Linux svr01 5.15.0 ...",
      "served_by": "llm",
      "exit_code": 0,
      "cwd": "/root"
    }
  ]
}
```

### `GET /api/stats`
Analytics summary.

```json
{
  "total_sessions": 128,
  "total_commands": 1422,
  "llm_call_rate": 0.36,
  "avg_commands_per_session": 11.1,
  "top_commands": [
    ["ls", 210],
    ["cat", 142],
    ["pwd", 98]
  ]
}
```

### `WS /api/stream`
WebSocket stream of live commands.

```json
{ "type": "command", "session_id": "a1b2c3", "input": "ls", "served_by": "fast-path", "ts": "2026-06-14T10:00:05Z", "exit_code": 0, "output": "..." }
```

## Development

### Frontend

```bash
cd dashboard/frontend
npm install
npm run dev
# Open http://localhost:5173
```

Dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.js`).

### Backend

Backend is part of the middleware. Ensure events log is written:

```bash
cd middleware
export SGLH_EVENTS_LOG=/tmp/events.json
python -m state_grounded.cowrie_bridge
```

Dashboard reads from `SGLH_EVENTS_LOG` environment variable.

## Docker

### Backend

```bash
docker build -f dashboard/backend/Dockerfile -t dashboard-backend .
docker run -p 8000:8000 -v /var/log/sglh:/var/log/sglh dashboard-backend
```

### Frontend

```bash
docker build -f dashboard/frontend/Dockerfile -t dashboard-frontend .
docker run -p 5173:5173 dashboard-frontend
```

### Docker Compose

See root [`docker-compose.yml`](../../docker-compose.yml) — includes middleware, Cowrie, and dashboard.

```bash
docker compose up dashboard
```

## Implementation Notes

- **State:** In-memory sessions dict. Can add SQLite index for historical analytics (W5).
- **WebSocket broadcaster:** Simple registry of connected clients; broadcasts new events.
- **Event ingestion:** Parses `events.json` (JSON-lines) on-demand; no intermediate DB.
- **CORS:** Basic OPTIONS handler for React dev server.
- **Backend:** Uses existing aiohttp server in `middleware/cowrie_bridge.py` (expanded with dashboard endpoints).

## Status

- ✅ Backend API implemented (SGLH-24)
- ✅ WebSocket live stream (SGLH-25)
- ✅ React UI (SGLH-26, 27, 28)
- 🔄 Integration testing with live Cowrie
- 🔄 UI polish & error handling
