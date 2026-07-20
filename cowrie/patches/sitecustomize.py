"""Monkey-patch Cowrie's LLM protocol to keep self.cwd in sync with the
middleware's authoritative state.

Installed as sitecustomize.py so Python loads it automatically at startup.
"""

import logging
import posixpath

logger = logging.getLogger(__name__)


def _resolve_cwd(current: str, target: str) -> str:
    if target == "/":
        return "/"
    if target == "~":
        return "/root"
    if target.startswith("~/"):
        return "/root/" + target[2:]
    if target.startswith("/"):
        return posixpath.normpath(target)
    return posixpath.normpath(posixpath.join(current, target))


def _apply_patch() -> None:
    try:
        import cowrie.llm.protocol as protocol

        original_handle = protocol.HoneyPotBaseProtocol._handle_llm_response

        def _patched_handle_llm_response(self, response: str) -> None:
            if self.command_history:
                last = self.command_history[-1]
                if last.startswith("User: "):
                    cmd = last[6:].strip()
                    parts = cmd.split(None, 1)
                    if parts and parts[0] == "cd" and response == "":
                        target = parts[1] if len(parts) > 1 else "/root"
                        self.cwd = _resolve_cwd(self.cwd, target)
            return original_handle(self, response)

        protocol.HoneyPotBaseProtocol._handle_llm_response = _patched_handle_llm_response
        logger.info("cwd-tracking patch applied to Cowrie LLM protocol")
    except Exception:
        logger.warning("cwd-tracking patch could not be applied", exc_info=True)


# Preserve the original apport hook if it was installed
try:
    import apport_python_hook  # noqa: F401
except ImportError:
    pass
else:
    apport_python_hook.install()

_apply_patch()