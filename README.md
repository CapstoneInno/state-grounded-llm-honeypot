# State-Grounded LLM Honeypot

A self-hosted deception layer for the [Cowrie](https://github.com/cowrie/cowrie)
SSH/Telnet honeypot with an embedded, **local** LLM (via [Ollama](https://ollama.com)).

LLM-powered honeypots already exist, but they share one documented weakness:
the model **loses track of session state** in multi-turn interactions. After
`mkdir /tmp/x`, a later `ls /tmp` may not show `x`; `cd /var && pwd` may lie.
These inconsistencies are the cheapest way for an attacker to fingerprint and
abandon the trap.

This project adds a **state-tracking middleware** between the attacker session
and the LLM. It maintains an authoritative model of the system (virtual
filesystem, current directory, environment variables, exit codes) and injects a
fresh state snapshot into the LLM context before every generation — so responses
stay consistent with the real session. Deterministic commands are answered
directly from the state engine (the **fast-path**), for both accuracy and speed,
and a deterministic guard rejects prompt-injection / non-command input before
the LLM is ever called.

It also ships an **admin dashboard** (aiohttp API + React) giving the operator a
live view of every interaction with the honeypot — sessions, commands, and
whether each command was served by the deterministic fast-path or the grounded
LLM.

> **Status:** Feature-complete (Week 6). State engine, prompt grounding,
> evaluation harness, and dashboard are implemented, tested (71 tests), and run
> end-to-end via a single `docker compose up`. See [Results](#results) for the
> measured before/after impact.

---

## Features

- **Authoritative state engine** — virtual filesystem (create/delete/modify),
  `cwd`, environment variables, and last exit code (`$?`), tracked per session
  and reset when the session ends.
- **Deterministic fast-path** — `pwd`, `cd`, `ls`, `mkdir`, `rmdir`, `rm`,
  `touch`, `echo`, `export`, `unset`, `whoami` are answered directly from the
  state engine: exact, instant, and never inconsistent — no LLM call.
- **Prompt grounding** — for everything else, the live state snapshot is
  injected into the LLM system prompt before each generation, plus few-shot
  turns that hold the model in character.
- **Prompt-injection guard** — conversational / instruction-shaped input is
  rejected as `command not found` *before* the LLM runs, so refusal is a
  property of the code, not the model's judgement.
- **Live admin dashboard** — sessions list, per-session command timeline with a
  ⚡ fast-path / 🧠 LLM badge and exit codes, analytics (LLM-call rate, top
  commands), and a WebSocket live feed.
- **Reproducible evaluation harness** — replays versioned scripted attacker
  sessions against the vanilla and grounded backends and scores state
  consistency, detection signals, latency, and LLM-call rate.
- **One-command self-hosted stack** — Ollama + model pull + middleware + Cowrie
  + dashboard via Docker Compose; no cloud, no weights in git.

---

## Architecture

```
attacker ──► Cowrie session ──► [State Middleware] ──► Ollama (local LLM)
                                      │   ▲
                                      ▼   │
                              authoritative session state:
                              - virtual filesystem (created/deleted/modified)
                              - cwd, env vars, exit code ($?)
                                      │
                                      ▼
                          prompt grounding: state snapshot injected
                          into the LLM context before each generation
```

Cowrie's built-in LLM backend speaks the OpenAI-compatible Chat Completions API.
The middleware **stands in the place Cowrie thinks is the LLM**: Cowrie's
`[llm] host/path` in `cowrie.cfg` point at the middleware bridge instead of
Ollama. For each command the bridge runs the fast-path/guard/LLM dispatch,
returns an OpenAI-shaped reply to Cowrie, and appends a `served_by`-tagged event
to the log the dashboard reads. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Tech stack

| Layer | Choice |
|---|---|
| Honeypot | Cowrie (upstream image, LLM backend) |
| Local LLM | Ollama, pinned model `qwen2.5:3b` (7–8B candidates supported) |
| Middleware + dashboard API | Python 3.12, `aiohttp` |
| Frontend | React 18 + Vite |
| Packaging | Docker Compose (5 services) |
| Tests / CI | pytest, ruff, GitHub Actions |

---

## Quick start (one command)

```bash
git clone https://github.com/CapstoneInno/state-grounded-llm-honeypot
cd state-grounded-llm-honeypot
cp .env.example .env
docker compose up -d --build      # or: bash scripts/setup.sh
```

The `ollama-pull` init container pulls and warms the pinned model
automatically — weights are **not** in git. First boot takes a few minutes
while the model downloads.

Then interact with the honeypot and watch it live:

```bash
ssh -p 2222 root@localhost        # any password is accepted
```

| Service | URL / port |
|---|---|
| Honeypot SSH | `ssh -p 2222 root@localhost` |
| Honeypot Telnet | `2223` |
| Middleware / API | http://localhost:8000 (`/healthz`, `/api/...`) |
| Admin dashboard | http://localhost:5173 |
| Ollama | http://localhost:11434 |

### Run the middleware demo without Docker

```bash
cd middleware
python -m pip install -r requirements.txt
python -m state_grounded          # prints a demo session-state snapshot
PYTHONPATH=src python -m pytest    # 71 tests pass
```

---

## Results

Measured with the evaluation harness over the versioned scripted attacker
sessions (see [`harness/`](harness/)), comparing the vanilla Cowrie LLM backend
against the state-grounded build, plus an ablation isolating each component.

| Metric | baseline (passthrough) | grounding only | fast-path only | **full** |
|---|---|---|---|---|
| State consistency rate (↑) | 0.125 | 0.500 | 1.000 | **1.000** |
| Detection rate (↓) | 0.097 | 0.056 | 0.000 | **0.000** |
| Detection signals (↓) | 7 | 4 | 0 | **0** |
| LLM call rate (↓) | 1.000 | 1.000 | 0.000 | **0.000** |
| Latency p95, s (↓) | 0.0060 | 0.0056 | 0.0030 | **0.0011** |

The grounded build eliminates the state-inconsistency signals that fingerprint
an LLM honeypot: state consistency rises from **12.5% → 100%**, detection
signals drop from **7 → 0**, and the deterministic fast-path serves the scripted
commands with **0 LLM calls** and lower tail latency. The ablation shows the
fast-path drives consistency and cost while grounding covers the non-
deterministic remainder. Reproduce with:

```bash
python harness/run_baseline.py --backend vanilla  --out harness/results/before.json
python harness/run_baseline.py --backend grounded --out harness/results/after.json
```

---

## Repository layout

```
state-grounded-llm-honeypot/
├── middleware/        # state engine, grounding, guard, Cowrie bridge + dashboard API (Python/aiohttp)
│   └── src/state_grounded/
│       ├── state_engine.py       # authoritative session state + fast-path
│       ├── prompt_grounding.py   # snapshot → LLM context; Ollama call
│       ├── dispatch.py           # fast-path / guard / LLM decision (served_by)
│       ├── cowrie_bridge.py      # OpenAI-compat endpoint + dashboard REST/WS
│       ├── ingest.py / models.py / events.py / config.py
│       └── tests/                # unit + smoke tests (pytest)
├── harness/           # reproducible before/after evaluation harness + sessions
├── cowrie/            # Cowrie config (points its LLM backend at the middleware)
├── dashboard/         # React + Vite admin UI (sessions, timeline, analytics)
├── docs/              # architecture, backlog, API contracts, reports
├── scripts/           # setup / model-pull helpers
├── docker-compose.yml # ollama + ollama-pull + middleware + cowrie + dashboard
├── .env.example
└── README.md
```

---

## Configuration

All configuration is environment-driven (`.env`, see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:3b` | Pinned model (reproducibility) |
| `MIDDLEWARE_FAST_PATH` | `true` | Serve deterministic commands from the state engine |
| `MIDDLEWARE_PROMPT_GROUNDING` | `true` | Inject the state snapshot into the prompt |
| `MIDDLEWARE_STRICT_COMMAND_GUARD` | `true` | Reject injection / non-command input pre-LLM |
| `COWRIE_SSH_PORT` / `COWRIE_TELNET_PORT` | `2222` / `2223` | Honeypot listeners |

Toggling `FAST_PATH` / `PROMPT_GROUNDING` off reproduces the ablation configs.

---

## API

The middleware exposes both the Cowrie-facing LLM endpoint and the dashboard API:

| Endpoint | Purpose |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible endpoint Cowrie calls |
| `GET /healthz` | Liveness check |
| `GET /api/sessions` | All sessions (IP, start time, command counts) |
| `GET /api/sessions/{id}` | Full command timeline for one session |
| `GET /api/stats` | Aggregate analytics (LLM-call rate, top commands) |
| `WS /api/stream` | Live command-event feed |

Full contracts: [`docs/api/dashboard-api.md`](docs/api/dashboard-api.md) and
[`docs/api/llm-backend-contract.md`](docs/api/llm-backend-contract.md).

---

## System requirements

| Resource | Minimum (3B model) | Recommended (7–8B model) |
|---|---|---|
| Disk | ~10 GB (Cowrie + one model) | ~15 GB |
| RAM / VRAM | ~4 GB | ~6–8 GB |
| Docker | Docker Engine + Compose v2 | same |

The full stack runs locally (no VM / cloud required).

---

## Team, track & contributions

Capstone team **CapstoneInno**. Track: **Research** (novel state-grounding
contribution + before/after evaluation) with an **Industrial** framing
(self-hostable deployment on top of the existing Cowrie product).

| Area | Lead(s) |
|---|---|
| State engine + fast-path | SNeka |
| Prompt grounding + injection hardening | Nikita |
| Evaluation harness + before/after study | Arseniy |
| Dashboard (API + React) + deployment/CI-CD | Denis |
| CI / build hardening + fixes | Pavel |
| Smoke tests / integration | Neialov |

> Update the leads above to match your team's final ownership.

---

## License

MIT (this project). Cowrie retains its BSD 3-Clause license. See [`LICENSE`](LICENSE).
