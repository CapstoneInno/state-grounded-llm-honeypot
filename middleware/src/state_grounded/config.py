from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    ollama_url: str
    ollama_model: str
    fast_path_only: bool
    events_log: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            ollama_url=os.getenv(
                "OLLAMA_URL",
                "http://localhost:11434",
            ),
            ollama_model=os.getenv(
                "OLLAMA_MODEL",
                "llama3.2",
            ),
            fast_path_only=os.getenv(
                "FAST_PATH_ONLY",
                "false",
            ).lower()
            == "true",
            events_log=os.getenv(
                "MIDDLEWARE_EVENTS_LOG",
                "var/sglh-events.jsonl",
            ),
        )
