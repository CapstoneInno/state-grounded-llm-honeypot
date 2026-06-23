"""Runnable demo week 2. Deterministic state engine.

Replays a short scripted session through the state engine and prints, after
each command, the grounded system prompt the LLM *would* receive. This proves deterministic state tracking and grounded-prompt generation on a scripted session.
Cowrie integration and live Ollama inference are the next project stage.

Run:  python -m state_grounded
"""

from __future__ import annotations

from .config import Config
from .prompt_grounding import build_grounded_prompt
from .state_engine import StateEngine

DEMO_SESSION = [
    "pwd",
    "mkdir /tmp/x",
    "cd /tmp",
    "mkdir notes",
    "ls",
    "export TARGET=10.0.0.7",
    "export MODE=scan",
    "cd notes",
    "echo $TARGET/$MODE",
    "cd /does-not-exist",
    "pwd",
    "cd ..",
    "rm notes",
    "rm -r notes",
    "unset MODE",
    "ls",
    "uname -a",
]

def main() -> None:
    config = Config.from_env()
    engine = StateEngine()

    print("=" * 64)
    print(" State-Grounded LLM Honeypot — Week 2 demo")
    print(f" model={config.ollama_model}  fast_path={config.fast_path}  "
          f"grounding={config.prompt_grounding}")
    print("=" * 64)

    for command in DEMO_SESSION:
        print(f"\n$ {command}")
        result = engine.try_fast_path(command) if config.fast_path else None
        if result is not None:
            if result:
                print(result)
            print(f"  [fast-path · no LLM call · exit={engine.last_exit_code}]")
        else:
            print("  [would call LLM — grounded prompt below]")
            grounded = build_grounded_prompt(engine.snapshot(), config)
            for line in grounded.splitlines():
                print(f"  | {line}")

    print("\n" + "-" * 64)
    print("Final snapshot:")
    for line in engine.snapshot().to_prompt_block().splitlines():
        print(f"  {line}")
    print("\nWeek 2 demo OK. Determenistic state runs successfully.")


if __name__ == "__main__":
    main()
