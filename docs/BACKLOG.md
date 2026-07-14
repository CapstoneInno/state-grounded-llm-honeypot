# Product Backlog & Kanban

Prioritized backlog for the 6-week build. Priorities: **P0** (must, MVP), **P1**
(should), **P3** (stretch). Importable version: [`backlog.csv`](backlog.csv).

> **Live board:** [Linear — CAP](https://linear.app/capstone-inno/team/CAP/active).
> This file mirrors it.

## Kanban snapshot (Week 6 — feature-complete)

All P0 and P1 stories are **Done**: the state engine, prompt grounding, guard,
dashboard, one-command Compose stack, CI/CD, and the before/after + ablation
evaluation are implemented, tested (71 tests, CI green), and run end-to-end
locally. Remaining work for Week 7 is report + video + minor polish only.

### ✅ Done

#### Setup & infrastructure
- **SGLH-3** · Setup · Repo scaffold (structure, README, .gitignore, LICENSE, runnable demo) · P0
- **SGLH-4** · Setup · Docker support (Dockerfile per component + docker-compose.yml) · P0
- **SGLH-1** · Setup · Cowrie LLM backend pointed at local Ollama via the middleware bridge · P0
- **SGLH-2** · Setup · Select & pin the LLM (`qwen2.5:3b` default; 7–8B candidates supported) · P0

#### Harness
- **SGLH-5** · Harness · Scripted-session format + versioned sample sessions · P0
- **SGLH-6** · Harness · Session runner + metric scoring (consistency, detection, latency, LLM-call rate) · P0
- **SGLH-7** · Harness · Record baseline ("before") on vanilla Cowrie + LLM · P0

#### State engine
- **SGLH-8** · State Engine · Virtual filesystem model (create/delete/modify) · P0
- **SGLH-9** · State Engine · Track cwd + basic env vars · P0
- **SGLH-10** · State Engine · Deterministic fast-path (`cd pwd mkdir rm touch ls rmdir`) · P0
- **SGLH-11** · State Engine · env (`export`/`unset`/`echo $VAR`), `$?`, `whoami` · P0

#### Integration & grounding
- **SGLH-12** · Integration · Integrate engine into Cowrie LLM command flow (bridge) · P0
- **SGLH-13** · Grounding · Inject state snapshot into LLM prompt · P0
- **SGLH-14** · Grounding · Basic response normalization / in-character fallback · P1
- **SGLH-15** · Grounding · End-to-end multi-turn smoke tests · P0

#### Dashboard
- **SGLH-24** · Dashboard · Backend API: read event log; `/api/sessions` + `/api/sessions/{id}` · P0
- **SGLH-25** · Dashboard · Live events feed (WebSocket `/api/stream`) · P0
- **SGLH-26** · Dashboard · React UI: sessions list (IP, start time, command count) · P0
- **SGLH-27** · Dashboard · React UI: per-session command timeline + fast-path/LLM badge · P0
- **SGLH-28** · Dashboard · Analytics view (commands/session, LLM-call rate, top commands) · P1

#### Evaluation
- **SGLH-16** · Evaluation · "After" numbers + before/after comparison · P0
- **SGLH-17** · Evaluation · Ablation study (fast-path / grounding contributions) · P0
- **SGLH-18** · Evaluation · Charts + results write-up (`ABLATION.md`, figures) · P1

#### Packaging & delivery
- **SGLH-19** · Packaging · One-command Compose deploy (full stack) · P0
- **SGLH-29** · Dashboard · Add dashboard to Compose; basic error handling · P0
- **SGLH-20** · Packaging · README sysreqs + setup; CI/tests · P1
- **SGLH-23** · Stretch · Deterministic prompt-injection guard + hardened system prompt · P3
- **CI/CD** · Delivery · GitHub Actions: lint + tests + docker build + self-hosted deploy w/ health-check

### 🔄 In progress / Week 7 (report + video only — no new features)
- **SGLH-21** · Delivery · Record demo video (vanilla loses state vs grounded holds it; show dashboard) · P0
- **SGLH-22** · Delivery · Finalize report; upstream PR/issue to Cowrie · P0

### 📋 Optional polish (only if time allows — respect code freeze)
- Silence aiohttp `AppKey` / deprecation warnings in the dashboard app.
- Sync `README` + `docs/api/*` wording with final endpoints (framework = aiohttp, not FastAPI).
- Commit a copy of `harness/results/*` + figures for reproducibility.

## Metrics achieved (before → full grounded)

| Metric | Baseline | Full | Direction |
|---|---|---|---|
| State consistency rate | 0.125 | 1.000 | ↑ |
| Detection signals | 7 | 0 | ↓ |
| LLM call rate | 1.000 | 0.000 | ↓ |
| Latency p95 (s) | 0.0060 | 0.0011 | ↓ |

## Definition of Done (per story)
Code merged via PR · unit/smoke tests pass · CI green · docs updated · no
secrets/model weights committed.

## Code freeze
Feature work is frozen at the end of Week 6. Week 7 is report + video + minor
fixes only. Final deadline: **22 July, 08:00 MSK**.
