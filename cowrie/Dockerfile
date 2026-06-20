# Cowrie image for the State-Grounded LLM Honeypot.
#
# We start from the official Cowrie image and bake in our LLM-backend config
# (etc/cowrie.cfg) which points Cowrie at the local Ollama service.
#
# NOTE on "fork": the course task says *fork* Cowrie. Forking is a GitHub action
# on your own account — click "Fork" on https://github.com/cowrie/cowrie. Once
# you have your fork and start changing Cowrie's source, switch the base below to
# a local build:
#
#   FROM python:3.12-slim
#   COPY . /cowrie-fork
#   RUN pip install --no-cache-dir -e /cowrie-fork
#
# Until then, this image runs upstream Cowrie with our config — fully runnable.
FROM cowrie/cowrie:latest

# Bake in our configuration (LLM backend → Ollama, JSON event log on).
COPY etc/cowrie.cfg /cowrie/cowrie-git/etc/cowrie.cfg
