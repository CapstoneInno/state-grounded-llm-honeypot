#!/usr/bin/env bash
# One-command bring-up. The ollama-pull init container pulls the pinned model
# automatically (see docker-compose.yml). Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

echo "==> Starting full stack (model pulled automatically by ollama-pull)..."
docker compose up -d --build

echo
echo "Done. Try the honeypot:"
echo "    ssh -p 2222 root@localhost      # any password is accepted"
