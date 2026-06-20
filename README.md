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
filesystem, current directory, environment variables, exit codes, process
table) and injects a fresh state snapshot into the LLM context before every
generation — so responses stay consistent with the real session. Deterministic
commands are answered directly from the state engine, for both accuracy and
speed.

It also ships an **admin dashboard** (FastAPI + React) giving the operator a
live view of every interaction with the honeypot — sessions, commands, and
whether each command was served by the deterministic fast-path or the grounded
LLM.

> **Status:** Week 1 — project scaffold + planning. The state engine, prompt
> grounding, and evaluation harness are stubs at this stage (see
> [`docs/WEEK1-REPORT.md`](docs/WEEK1-REPORT.md) and
> [`docs/BACKLOG.md`](docs/BACKLOG.md)).

---

## Architecture

```
attacker ──► Cowrie session ──► [State Middleware] ──► Ollama (local LLM)
                                      │   ▲
                                      ▼   │
                              authoritative session state:
                              - virtual filesystem (created/deleted/modified)
                              - cwd, env vars, exit code ($?), users
                              - process table / PIDs
                                      │
                                      ▼
                          prompt grounding: state snapshot injected
                          into the LLM context before each generation
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

---

## Repository layout

```
state-grounded-llm-honeypot/
├── middleware/        # state engine + prompt grounding (Python)
│   ├── src/state_grounded/
│   │   ├── __main__.py          # runnable demo (Hello World)
│   │   ├── state_engine.py      # authoritative session state (skeleton)
│   │   ├── prompt_grounding.py  # snapshot → LLM context (skeleton)
│   │   └── config.py            # env-driven configuration
│   ├── tests/                   # unit tests (pytest)
│   ├── Dockerfile
│   └── requirements.txt
├── harness/           # reproducible evaluation harness (skeleton)
│   ├── sessions/      # versioned scripted attacker sessions (sample)
│   └── run_baseline.py
├── cowrie/            # Cowrie fork goes here (added Week 1; see cowrie/README.md)
├── dashboard/         # admin dashboard — FastAPI backend + React frontend (planned, W3-6)
├── docs/              # report, backlog, architecture, API contracts
├── scripts/           # helper scripts
├── docker-compose.yml # cowrie + ollama + middleware, one command
├── .env.example
└── README.md
```

---

## Quick start (Week 1 scaffold)

The scaffold is **runnable today** even before Cowrie/Ollama are wired in — it
prints a demo state snapshot so you can confirm the toolchain works.

### Run the demo locally (no Docker)

```bash
git clone https://github.com/SSSNeka/state-grounded-llm-honeypot
cd state-grounded-llm-honeypot/middleware
python -m pip install -r requirements.txt
python -m state_grounded            # prints a demo session-state snapshot
python -m pytest                    # smoke tests pass
```

### Run with Docker

```bash
cp .env.example .env
docker compose up --build middleware   # runs the demo in a container
```

Run Cowrie with the local LLM (Ollama):

```bash
cp .env.example .env
bash scripts/setup.sh        # starts Ollama, pulls the model, launches Cowrie
ssh -p 2222 root@localhost   # connect as an "attacker" (any password works)
```

The model is pulled with `ollama pull` at setup — weights are NOT in git. See
[`cowrie/README.md`](cowrie/README.md) for details and the fork step.

---

## System requirements (planned)

| Resource | Minimum (3B model) | Recommended (7–8B model) |
|---|---|---|
| Disk | ~10 GB (Cowrie + one model) | ~15 GB |
| RAM / VRAM | ~4 GB | ~6–8 GB |
| Docker | Docker Engine + Compose v2 | same |

---

## Roadmap

| Week | Milestone |
|---|---|
| 1 | Scaffold, plan, harness skeleton, baseline ("before") |
| 2–3 | State engine implemented & integrated into Cowrie |
| 3 | Dashboard backend serving live honeypot events |
| 4 | Prompt grounding → working "after" build; dashboard UI (live interactions) |
| 5 | Before/after results + ablation study; dashboard analytics |
| 6 | Self-hosted package (incl. dashboard) + demo + upstream PR |

See [`docs/WEEK1-REPORT.md`](docs/WEEK1-REPORT.md) for the full week-by-week plan,
requirements, and tech-stack justification.

## License

MIT (this project). Cowrie retains its BSD 3-Clause license. See [`LICENSE`](LICENSE).
