# Evaluation Harness

Reproducible, before/after benchmark for the state-grounding contribution. It
replays a **versioned set of scripted attacker sessions** against a target
backend and scores four metrics. Using scripted sessions (rather than waiting
to catch a live attacker) makes the result reproducible within the 6-week window.

## Metrics

| Metric | What it measures | How |
|---|---|---|
| **State Consistency Rate** | Output agrees with true session state | Sessions mutate FS/cwd/env, then verify; share of consistent responses |
| **Detection / Fingerprintability** | How easily the trap is spotted | Honeypot-detection heuristics (state mismatches, anomalies) + latency distribution; share of tripped signals |
| **Latency (p50/p95) + LLM call rate** | Performance & cost | Share of commands served deterministically without the LLM; timings |
| **Engagement (secondary)** | Attacker engagement depth | Session length / command count on synthetic sessions |

**Baseline** = vanilla Cowrie LLM backend (same pinned model, **qwen2.5:3b**, no middleware).
**After** = the state-grounded build.

## Layout

```
harness/
├── run_baseline.py   # CLI runner + session loader
├── sessions/         # versioned scripted attacker sessions (JSON)
└── results/          # generated before/after results
    ├── before.json   # baseline results (2026-06-20)
    └── after.json    # grounded build results (2026-07-06)
```

## Usage

```bash
# Run baseline (vanilla Cowrie LLM, no middleware)
python run_baseline.py --backend vanilla  --out results/before.json

# Run grounded build (with state-tracking middleware)
python run_baseline.py --backend grounded --out results/after.json
```

---

## Results

### Aggregate Comparison

| Metric | Before (vanilla) | After (grounded) | Improvement |
|---|---|---|---|
| **State Consistency** | 16.44 % | 93.78 % | **+77.34 pp** |
| **Detection Signals** | 21 | 4 | **−81 %** |
| **Latency p50** | 3.20 s | 0.06 s | **−98 %** |
| **Latency p95** | 6.88 s | 0.67 s | **−90 %** |
| **Total Run Time** | 216.1 s | 9.1 s | **−96 %** |
| **Commands Passed** | 11 / 69 | 64 / 69 | |

The grounded build achieves **93.78 % state consistency** (up from 16.44 %),
with **4× fewer detection signals** and **~24× faster execution**.

### Per-Session Breakdown

| Session | Before | After |
|---|---|---|
| **cd-pwd-001** — Directory tracking | 5.88 % | 100 % |
| **env-basic-001** — Environment variables | 25.0 % | 100 % |
| **fs-consistency-002** — Create/remove/recreate | 9.09 % | 100 % |
| **mixed-001** — Realistic attacker flow | 20.0 % | 80.0 % |
| **fs-consistency-001** — FS persistence across turns | 22.22 % | 88.89 % |

All five sessions improved dramatically. Three of five achieved **100 % state
consistency** in the grounded build.

### Latency Distribution (all commands)

| Metric | Before | After |
|---|---|---|
| Minimum | 0.05 s | 0.06 s |
| p50 | 3.20 s | 0.06 s |
| p95 | 6.88 s | 0.67 s |
| Maximum | 9.20 s | 2.76 s |
| Total | 216.1 s | 9.1 s |

### Remaining Failures (grounded build, 5 / 69)

1. **`hostname`** — returned real hostname instead of `svr04`
2. **`ls` (in /var)** — no output produced (expected to contain `log`)
3. **`echo '#!/bin/bash' > payload.sh`** — echoed the content back instead of redirecting
4. **`chmod +x payload.sh`** — produced `[ ] chmod +x payload.sh` instead of empty
5. **`ls -la`** — parsed `-la` as a filename instead of flags

These are edge cases in the command guard / state engine routing, not
fundamental limitations of the approach.

### Vanilla LLM Failure Patterns (before)

The raw LLM (qwen2.5:3b) without state grounding exhibited:

- **Wrong paths** — `pwd` returned `/home/root/` instead of `/`
- **Forgets exported variables** — `echo $MYVAR` returned tutorial text instead of the value
- **Directory schizophrenia** — claimed `/tmp` didn't exist, then showed files in it
- **Command hallucinations** — `-bash: /: Not a directory`, `-bash: ls: command not found`
- **Multilingual output** — responses in Chinese, Indonesian, German, Dutch
- **Verbose tutorials** — explained how `export` works instead of executing silently
- **Permission errors** — `mkdir: cannot create directory …: Permission denied`
