# Report section — Cowrie + Ollama Integration and Reproduced Baseline Problem

> Drop-in section for the Week 1 report. Pairs with a screenshot of the SSH
> session described below. English to match the submitted report; a LaTeX
> version is trivial to derive (same headings/itemize).

## Cowrie + Ollama Integration

We integrated the target product, the Cowrie SSH/Telnet honeypot, with a local
LLM served by Ollama. Cowrie's experimental LLM backend speaks the
OpenAI-compatible API, so we point it at the local Ollama endpoint
(`host = http://ollama:11434`, `path = /v1/chat/completions`,
`model = qwen2.5:3b`). The whole stack runs locally via Docker Compose; no
external API is used and the model weights are pulled at setup with `ollama pull`
(never committed to git). Bringing the system up and connecting takes three
commands:

```bash
cp .env.example .env
bash scripts/setup.sh          # start Ollama, pull the model, launch Cowrie
ssh -p 2222 root@localhost     # any login/password is accepted
```

The honeypot accepts any credentials by design — its purpose is to admit and
observe an attacker. Every command and session is written to a structured JSON
event log (`var/log/cowrie/cowrie.json`), which is the stream our admin
dashboard will consume in Weeks 3–6.

## Reproduced Baseline Problem (state drift)

Connecting as `root` and running a short sequence immediately reproduces the
documented weakness of LLM honeypots — **state drift**. The vanilla LLM backend
has no authoritative filesystem; it generates each response as text, so its
answers contradict reality and one another. Observed session:

```
root@svr04:/# mkdir /tmp/x
mkdir: cannot create directory '/tmp/x': Permission denied
root@svr04:/# ls /tmp
ls: cannot access '/tmp': No such file or directory
/tmp/x: created
root@svr04:/# mkdir /tmp/x
mkdir: cannot create directory '/tmp/x': Permission denied
```

This output is internally inconsistent and factually wrong:

- **`mkdir` → "Permission denied" as root.** The `root` user always has write
  access to `/tmp`; this command should succeed silently.
- **`/tmp` reported as non-existent.** `/tmp` exists on every Linux system; the
  model denies it.
- **Self-contradiction in a single response.** The same `ls /tmp` claims `/tmp`
  does not exist *and* that `/tmp/x` was created.
- **No memory of state.** The repeated `mkdir` is treated inconsistently; there
  is no persistent notion of what exists.

Cowrie's own documentation confirms the cause: the LLM backend "maintains the
last 10 commands" of context and "may occasionally be inconsistent with
filesystem state." An attacker needs only two or three commands to detect these
contradictions and abandon the trap.

## Why this matters for our contribution

This live reproduction is our **baseline ("before")** evidence: the unmodified
LLM backend fails on basic, multi-turn filesystem consistency. Our contribution
— an authoritative state engine (virtual filesystem, cwd, env, exit codes) plus
prompt grounding — is designed to eliminate exactly these contradictions.
Weeks 2–3 build the state engine; Week 4 grounds the LLM; Week 5 quantifies the
improvement on the same reproducible benchmark (state consistency rate,
detectability, latency, LLM call rate).

*Note on reproducibility:* measurements use a pinned model (`qwen2.5:3b`) with
default decoding settings, recorded in `cowrie/etc/cowrie.cfg`. A small model
makes the drift more visible, which is acceptable for demonstrating the problem;
the before/after comparison uses the same model on both sides.
