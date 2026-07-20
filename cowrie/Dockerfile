FROM cowrie/cowrie:latest

# Bake in our configuration (LLM backend → Ollama, JSON event log on).
COPY etc/cowrie.cfg /cowrie/cowrie-git/etc/cowrie.cfg

# Apply cwd-tracking monkey-patch so the shell prompt shows the real directory.
# Python auto-loads sitecustomize.py during site initialization.
# We overwrite the system sitecustomize (apport hook is preserved inside).
COPY patches/sitecustomize.py /usr/lib/python3.13/sitecustomize.py