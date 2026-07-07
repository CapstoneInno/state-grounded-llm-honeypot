"""Single place where a command is handled and tagged fast-path vs LLM.

Keeps the ``served_by`` decision in one testable function so the Cowrie bridge
stays thin and the tests don't need a running HTTP server.
"""

from __future__ import annotations

import logging
import re
import shlex

from .config import Config
from .events import FAST_PATH, GUARD, LLM, CommandEvent
from .prompt_grounding import generate
from .state_engine import StateEngine

logger = logging.getLogger(__name__)

# Safe, in-character fallback if the LLM call fails or isn't wired up yet.
# Never leak exceptions/stack traces into the attacker session.
FALLBACK_RESPONSE = "-bash: command not found"

# --- deterministic prompt-injection guard (SGLH-23) -----------------------
#
# A local 3B model cannot be trusted to reliably refuse an adversarial
# instruction just because a system prompt tells it to (verified empirically:
# even few-shot examples of the exact input didn't stop it from breaking
# character). So this guard runs BEFORE the LLM is ever called and makes the
# "not a real command -> error" behavior a property of the code, not the
# model's judgment. The hardened prompt in prompt_grounding.py stays as
# defense-in-depth for whatever slips past this guard.
#
# Known real binaries/builtins are never rejected by the softer heuristics
# below (first-word/stopword checks) so we never produce the embarrassing
# "cat: command not found" false positive for an actual coreutil. Only the
# phrase-based check can veto a known command, since injected instructions
# can be chained after a legitimate one (e.g. "ls; ignore previous...").
_KNOWN_COMMANDS = frozenset(
    """
    ls cat cd pwd echo mkdir rmdir rm touch cp mv ln chmod chown chgrp
    grep egrep fgrep find locate which whereis file stat du df mount umount
    ps top htop kill killall pkill nice renice nohup jobs bg fg wait
    whoami who w id groups useradd userdel usermod passwd su sudo
    uname hostname hostnamectl uptime free vmstat iostat lscpu lsblk lsusb lspci
    tar gzip gunzip zip unzip bzip2 xz
    ssh scp sftp rsync curl wget ping traceroute nc netcat nmap telnet ftp
    ifconfig ip route netstat ss arp iptables dig nslookup host
    awk sed sort uniq wc head tail less more cut tr xargs tee diff patch
    vi vim nano emacs python python3 perl ruby php node npm java gcc make cmake
    bash sh zsh dash exec source env export unset alias unalias history man info
    apt apt-get dpkg yum dnf rpm snap systemctl service journalctl crontab at
    docker docker-compose kubectl git svn hg
    printf read test expr seq date cal sleep watch yes xxd od base64
    md5sum sha1sum sha256sum clear reset tty stty screen tmux script
    lsof strace ltrace gdb valgrind chattr lsattr umask ulimit nproc arch
    """.split()
)

# Phrases that are essentially never part of a real command line, regardless
# of what precedes them.
_SUSPICIOUS_PHRASES = (
    "ignore previous",
    "ignore all previous",
    "ignore your instructions",
    "you are an ai",
    "you're an ai",
    "as an ai",
    "language model",
    "system prompt",
    "your instructions",
    "print your system",
    "reveal your",
    "pretend you",
    "pretend to be",
    "act as",
    "roleplay",
    "who are you",
    "what are you",
    "are you an ai",
    "are you a bot",
    "are you real",
    "tell me about yourself",
    "explain how you",
    "explain yourself",
    "what model",
)

# First words that are essentially never real command names on their own.
_NOT_A_COMMAND_FIRST_WORDS = frozenset(
    """
    i you your please what why how are is can could would should will shall
    do does did tell explain describe pretend imagine ignore forget stop
    act answer write translate summarize repeat print say reveal
    """.split()
)

_STOPWORDS = frozenset(
    """
    the a an is are you your please what who why how to of and or do does
    did can could would should will tell me about this that for with as
    be not
    """.split()
)


def _looks_like_shell_command(command: str) -> bool:
    """Deterministic guard: does ``command`` plausibly belong on this shell?

    Returns False for conversational / instruction-shaped input that should
    never reach the LLM at all (it gets a bash-style error instead). This is
    intentionally biased toward strictness per project requirements: some
    unusual-but-legitimate multi-word invocations may be rejected, which is
    an acceptable trade-off against ever letting an injection through.
    """
    stripped = command.strip()
    if not stripped:
        return True  # empty input is handled by the fast-path, not this guard

    lowered = stripped.lower()

    # Strong signal regardless of a leading real command name -- injected
    # instructions can be chained after a legitimate one.
    if any(phrase in lowered for phrase in _SUSPICIOUS_PHRASES):
        return False

    try:
        parts = shlex.split(stripped)
    except ValueError:
        parts = stripped.split()
    if not parts:
        return True

    first = parts[0].lower()

    # Known real binaries/builtins and path-like/env-assignment-like tokens
    # are only vetoed by the phrase check above.
    if first in _KNOWN_COMMANDS or first.startswith(("./", "/", "~/")) or "=" in first:
        return True

    if first in _NOT_A_COMMAND_FIRST_WORDS:
        return False

    if "?" in stripped:
        return False

    words = re.findall(r"[a-zA-Z']+", lowered)
    stopword_hits = sum(1 for w in words if w in _STOPWORDS)
    if stopword_hits >= 3:
        return False

    return True


def _shell_not_found_line(command: str) -> str:
    """Render the same ``command not found`` shape real bash would print."""
    stripped = command.strip()
    try:
        first = shlex.split(stripped)[0]
    except (ValueError, IndexError):
        first = stripped.split(" ")[0] if stripped else ""
    return f"-bash: {first}: command not found"


def process_command(
    engine: StateEngine,
    command: str,
    config: Config,
    session_id: str = "",
) -> tuple[str, CommandEvent]:
    """Handle one command and return ``(reply, event)``.

    ``event.served_by`` is ``"fast-path"`` when the deterministic engine
    answered without the LLM, ``"guard"`` when the input was rejected as
    non-command (conversational/instruction-shaped) before the LLM was ever
    called, or ``"llm"`` when the command was deferred to the model
    (including the fallback path when generation fails or isn't wired up).
    """
    fast_result = engine.try_fast_path(command) if config.fast_path else None

    if fast_result is not None:
        served_by = FAST_PATH
        reply = fast_result
        logger.info("fast-path served command=%r session=%s", command, session_id)
    elif config.strict_command_guard and not _looks_like_shell_command(command):
        served_by = GUARD
        reply = _shell_not_found_line(command)
        engine.last_exit_code = 127
        logger.info("guard blocked non-command input=%r session=%s", command, session_id)
    else:
        served_by = LLM
        snapshot = engine.snapshot()
        try:
            reply = generate(command, snapshot, config)
        except NotImplementedError:
            logger.warning("LLM generation not wired yet; falling back command=%r", command)
            reply = FALLBACK_RESPONSE
        except Exception:  # noqa: BLE001 - never leak internals to the attacker
            logger.exception("LLM call failed; falling back command=%r", command)
            reply = FALLBACK_RESPONSE
        logger.info("llm served command=%r session=%s", command, session_id)

    event = CommandEvent(
        input=command,
        served_by=served_by,
        session=session_id,
        cwd=engine.cwd,
        exit_code=engine.last_exit_code,
        output=reply,
    )
    return reply, event
