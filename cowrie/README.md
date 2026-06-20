# Cowrie + Ollama

This is the **target product** for our Industrial contribution: the
[Cowrie](https://github.com/cowrie/cowrie) SSH/Telnet honeypot, running with its
**experimental LLM backend pointed at a local Ollama**. Our state-tracking
middleware plugs into this LLM command flow in Weeks 2-4.

## What's wired up

- `Dockerfile` — official Cowrie image with our config baked in.
- `etc/cowrie.cfg` — enables `backend = llm` and points it at the `ollama`
  service (`host = http://ollama:11434`, `path = /v1/chat/completions`,
  `model = qwen2.5:3b`). JSON event log is on (the stream the dashboard reads).

Cowrie's LLM backend speaks the OpenAI-compatible API; Ollama serves one and
ignores the API key, so any non-empty `api_key` works.

## Run it (on your machine — needs Docker + Ollama weights)

From the repo root:

```bash
cp .env.example .env
bash scripts/setup.sh        # starts Ollama, pulls the model, launches Cowrie
```

Then connect as an "attacker":

```bash
ssh -p 2222 root@localhost   # any password is accepted
# try:  mkdir /tmp/x   then later:  ls /tmp
```

Watch the events the dashboard will consume:

```bash
docker compose exec cowrie tail -f var/log/cowrie/cowrie.json
```

> This is exactly where our gap shows: with the **vanilla** LLM backend, after
> `mkdir /tmp/x` a later `ls /tmp` often won't show `x` — Cowrie's docs note it
> "maintains the last 10 commands" and "may be inconsistent with filesystem
> state." That's what our middleware fixes (Weeks 2-4).

## The "fork" step (yours — needs your GitHub account)

The task says *fork* Cowrie. That's a one-click action on your account:

1. Open https://github.com/cowrie/cowrie and click **Fork**.
2. Once you start editing Cowrie's source, vendor your fork here:
   ```bash
   git submodule add https://github.com/<your-user>/cowrie cowrie/upstream
   ```
   and switch `Dockerfile` to a local build (see the comment in `Dockerfile`).

Until you modify Cowrie's source, the image above runs upstream Cowrie with our
config — fully functional for integration and baseline measurement.

License: Cowrie is BSD-3-Clause; the fork retains it.
