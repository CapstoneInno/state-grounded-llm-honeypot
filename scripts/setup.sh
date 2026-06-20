#!/usr/bin/env bash
# One-command bring-up: start Ollama, pull the pinned model, then launch Cowrie
# (its LLM backend talks to the local Ollama). Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env
MODEL="$(grep -E '^OLLAMA_MODEL=' .env | cut -d= -f2)"
MODEL="${MODEL:-qwen2.5:3b}"

echo "==> Starting Ollama..."
docker compose up -d ollama

echo "==> Waiting for Ollama to be healthy..."
until docker compose exec -T ollama ollama list >/dev/null 2>&1; do sleep 2; done

echo "==> Pulling pinned model: ${MODEL} (weights are NOT in git)"
docker compose exec -T ollama ollama pull "${MODEL}"

echo "==> Starting Cowrie (LLM backend -> Ollama)..."
docker compose up -d --build cowrie

echo
echo "Done. Try the honeypot:"
echo "    ssh -p 2222 root@localhost      # any password is accepted"
echo "Watch the event log the dashboard will read:"
echo "    docker compose exec cowrie tail -f var/log/cowrie/cowrie.json"
