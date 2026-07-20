"""Authoritative session-state engine."""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass

_VAR_PATTERN = re.compile(r"\$\{(\w+)\}|\$(\w+)")


@dataclass
class _VfsNode:
    kind: str
    mode: int = 0o755

    @property
    def is_dir(self) -> bool:
        return self.kind == "dir"

    @property
    def mode_str(self) -> str:
        if self.is_dir:
            return "d" + self._perm_str(self.mode)
        return "-" + self._perm_str(self.mode)

    @staticmethod
    def _perm_str(mode: int) -> str:
        r = ""
        for who in (6, 3, 0):
            m = (mode >> who) & 7
            r += "r" if m & 4 else "-"
            r += "w" if m & 2 else "-"
            r += "x" if m & 1 else "-"
        return r


@dataclass
class StateSnapshot:
    """An immutable view of session state, injected into the LLM context."""

    cwd: str
    files_here: list[str]
    env: dict[str, str]
    last_exit_code: int

    def to_prompt_block(self) -> str:
        """Render the snapshot as a compact block for the system prompt."""
        files = " ".join(sorted(self.files_here)) or "(empty)"
        env = ", ".join(f"{k}={v}" for k, v in sorted(self.env.items())) or "(none)"
        return (
            "## CURRENT SESSION STATE (authoritative — never contradict this)\n"
            f"cwd: {self.cwd}\n"
            f"files in cwd: {files}\n"
            f"env: {env}\n"
            f"last exit code ($?): {self.last_exit_code}\n"
        )


class StateEngine:
    """Tracks the authoritative state of one attacker session."""

    def __init__(self) -> None:
        self._nodes: dict[str, _VfsNode] = {"/": _VfsNode("dir")}
        self._children: dict[str, set[str]] = {"/": set()}
        for path in (
            "/bin",
            "/boot",
            "/dev",
            "/etc",
            "/etc/ssh",
            "/etc/systemd",
            "/etc/nginx",
            "/etc/apt",
            "/etc/cron.d",
            "/home",
            "/home/user",
            "/home/user/Desktop",
            "/home/user/Documents",
            "/home/user/Downloads",
            "/home/user/Music",
            "/home/user/Pictures",
            "/home/user/Videos",
            "/home/user/Public",
            "/home/user/Templates",
            "/lib",
            "/media",
            "/mnt",
            "/opt",
            "/proc",
            "/root",
            "/root/Desktop",
            "/root/Documents",
            "/root/Downloads",
            "/root/Music",
            "/root/Pictures",
            "/root/Videos",
            "/root/Public",
            "/root/Templates",
            "/run",
            "/sbin",
            "/srv",
            "/sys",
            "/tmp",
            "/usr",
            "/usr/bin",
            "/usr/lib",
            "/usr/local",
            "/usr/share",
            "/usr/include",
            "/var",
            "/var/log",
            "/var/tmp",
            "/var/cache",
            "/var/lib",
            "/var/spool",
        ):
            self._add_dir(path)

        self.cwd: str = "/"
        self.env: dict[str, str] = {"HOME": "/root", "USER": "root", "PWD": "/"}
        self.last_exit_code: int = 0

    # --- snapshot --------------------------------------------------------
    def snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            cwd=self.cwd,
            files_here=self._list_children(self.cwd),
            env=dict(self.env),
            last_exit_code=self.last_exit_code,
        )

    # --- deterministic fast-path ----------------------------------------
    def try_fast_path(self, command: str) -> str | None:
        """Resolve a deterministic command from state, or return None."""
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            self.last_exit_code = 1
            return f"bash: {exc}"

        if not parts:
            self.last_exit_code = 0
            return ""

        cmd, args = parts[0], parts[1:]

        if cmd == "pwd":
            return self._handle_pwd(args)
        if cmd == "cd":
            return self._handle_cd(args)
        if cmd == "export":
            return self._handle_export(args)
        if cmd == "unset":
            return self._handle_unset(args)
        if cmd == "echo":
            return self._handle_echo(args)
        if cmd == "mkdir":
            return self._handle_mkdir(args)
        if cmd == "ls":
            return self._handle_ls(args)
        if cmd == "touch":
            return self._handle_touch(args)
        if cmd == "rmdir":
            return self._handle_rmdir(args)
        if cmd == "rm":
            return self._handle_rm(args)
        if cmd == "whoami":
            return self._handle_whoami(args)
        if cmd == "chmod":
            return self._handle_chmod(args)

        return None

    # --- command handlers ------------------------------------------------
    def _handle_pwd(self, args: list[str]) -> str:
        if args:
            self.last_exit_code = 1
            return "pwd: too many arguments"
        self.last_exit_code = 0
        return self.cwd

    def _handle_cd(self, args: list[str]) -> str:
        if len(args) > 1:
            self.last_exit_code = 1
            return "bash: cd: too many arguments"

        raw_target = args[0] if args else self.env["HOME"]
        target = self._resolve_path(raw_target)
        node = self._nodes.get(target)
        if node is None:
            self.last_exit_code = 1
            return f"bash: cd: {raw_target}: No such file or directory"
        if not node.is_dir:
            self.last_exit_code = 1
            return f"bash: cd: {raw_target}: Not a directory"

        self.cwd = target
        self.env["PWD"] = target
        self.last_exit_code = 0
        return ""

    def _handle_export(self, args: list[str]) -> str:
        if len(args) != 1 or "=" not in args[0]:
            self.last_exit_code = 1
            return "export: usage: export NAME=value"

        name, value = args[0].split("=", 1)
        if not self._is_valid_var_name(name):
            self.last_exit_code = 1
            return f"export: `{name}`: not a valid identifier"

        self.env[name] = self._substitute_vars(value)
        self.last_exit_code = 0
        return ""

    def _handle_unset(self, args: list[str]) -> str:
        if len(args) != 1:
            self.last_exit_code = 1
            return "unset: usage: unset NAME"
        if not self._is_valid_var_name(args[0]):
            self.last_exit_code = 1
            return f"unset: `{args[0]}`: not a valid identifier"

        self.env.pop(args[0], None)
        self.last_exit_code = 0
        return ""

    def _handle_echo(self, args: list[str]) -> str:
        self.last_exit_code = 0
        return " ".join(self._substitute_vars(arg) for arg in args)

    def _handle_mkdir(self, args: list[str]) -> str:
        if not args:
            self.last_exit_code = 1
            return "mkdir: missing operand"
        if len(args) != 1 or args[0].startswith("-"):
            self.last_exit_code = 1
            return f"mkdir: invalid option -- '{args[0]}'"

        raw_target = args[0]
        target = self._resolve_path(raw_target)
        if target in self._nodes:
            self.last_exit_code = 1
            return f"mkdir: cannot create directory '{raw_target}': File exists"

        parent, name = self._split(target)
        parent_node = self._nodes.get(parent)
        if parent_node is None:
            self.last_exit_code = 1
            return f"mkdir: cannot create directory '{raw_target}': No such file or directory"
        if not parent_node.is_dir:
            self.last_exit_code = 1
            return f"mkdir: cannot create directory '{raw_target}': Not a directory"
        if not name:
            self.last_exit_code = 1
            return f"mkdir: cannot create directory '{raw_target}': File exists"

        self._add_dir(target)
        self.last_exit_code = 0
        return ""

    def _handle_ls(self, args: list[str]) -> str:
        flags = set()
        targets: list[str] = []
        for arg in args:
            if arg.startswith("-") and arg != "-":
                for flag in arg[1:]:
                    flags.add(flag)
            else:
                targets.append(arg)

        if len(targets) > 1:
            self.last_exit_code = 1
            return "ls: too many arguments"

        raw_target = targets[0] if targets else self.cwd
        target = self._resolve_path(raw_target)
        node = self._nodes.get(target)
        if node is None:
            self.last_exit_code = 1
            return f"ls: cannot access '{raw_target}': No such file or directory"

        self.last_exit_code = 0
        if node.is_dir:
            if "d" in flags:
                return self._format_entry(target)
            children = self._list_children(target)
            if "a" in flags:
                children = [".", ".."] + children
            if "l" in flags:
                return self._format_long_list(children, target)
            return "  ".join(children)
        if "l" in flags:
            return self._format_entry(target)
        return posixpath.basename(target)

    def _format_entry(self, path: str) -> str:
        node = self._nodes.get(path)
        if node is None:
            return ""
        name = posixpath.basename(path) if path != "/" else "/"
        return f"{node.mode_str} 1 root root 4096 Jul 21 12:00 {name}"

    def _format_long_list(self, children: list[str], dir_path: str) -> str:
        lines = []
        for name in children:
            if name == ".":
                lines.append("drwxr-xr-x 2 root root 4096 Jul 21 12:00 .")
            elif name == "..":
                lines.append("drwxr-xr-x 2 root root 4096 Jul 21 12:00 ..")
            else:
                full = self._join(dir_path, name)
                lines.append(self._format_entry(full))
        return "\n".join(lines)

    def _handle_touch(self, args: list[str]) -> str:
        if len(args) != 1:
            self.last_exit_code = 1
            return "touch: missing file operand"

        raw_target = args[0]
        target = self._resolve_path(raw_target)
        node = self._nodes.get(target)
        if node is not None:
            self.last_exit_code = 0
            return ""

        parent, name = self._split(target)
        parent_node = self._nodes.get(parent)
        if parent_node is None:
            self.last_exit_code = 1
            return f"touch: cannot touch '{raw_target}': No such file or directory"
        if not parent_node.is_dir:
            self.last_exit_code = 1
            return f"touch: cannot touch '{raw_target}': Not a directory"
        if not name:
            self.last_exit_code = 1
            return f"touch: cannot touch '{raw_target}': Invalid argument"

        self._add_file(target)
        self.last_exit_code = 0
        return ""

    def _handle_rmdir(self, args: list[str]) -> str:
        if len(args) != 1:
            self.last_exit_code = 1
            return "rmdir: missing operand"

        raw_target = args[0]
        target = self._resolve_path(raw_target)
        node = self._nodes.get(target)
        if node is None:
            self.last_exit_code = 1
            return f"rmdir: failed to remove '{raw_target}': No such file or directory"
        if not node.is_dir:
            self.last_exit_code = 1
            return f"rmdir: failed to remove '{raw_target}': Not a directory"
        if target == "/":
            self.last_exit_code = 1
            return "rmdir: failed to remove '/': Device or resource busy"
        if self._is_ancestor(target, self.cwd):
            self.last_exit_code = 1
            return f"rmdir: failed to remove '{raw_target}': Device or resource busy"
        if self._children.get(target):
            self.last_exit_code = 1
            return f"rmdir: failed to remove '{raw_target}': Directory not empty"

        self._remove_subtree(target)
        self.last_exit_code = 0
        return ""

    def _handle_rm(self, args: list[str]) -> str:
        if not args:
            self.last_exit_code = 1
            return "rm: missing operand"

        recursive = False
        force = False
        targets: list[str] = []
        for arg in args:
            if arg.startswith("-") and arg != "-":
                for flag in arg[1:]:
                    if flag == "r" or flag == "R":
                        recursive = True
                        continue
                    if flag == "f":
                        force = True
                        continue
                    self.last_exit_code = 1
                    return f"rm: invalid option -- '{arg}'"
                continue
            targets.append(arg)

        if len(targets) != 1:
            self.last_exit_code = 1
            return "rm: missing operand"

        raw_target = targets[0]
        target = self._resolve_path(raw_target)
        node = self._nodes.get(target)
        if node is None:
            self.last_exit_code = 0 if force else 1
            if force:
                return ""
            return f"rm: cannot remove '{raw_target}': No such file or directory"
        if target == "/":
            self.last_exit_code = 1
            return "rm: refusing to remove root directory '/'"
        if self._is_ancestor(target, self.cwd):
            self.last_exit_code = 1
            return f"rm: cannot remove '{raw_target}': Device or resource busy"
        if node.is_dir and not recursive:
            self.last_exit_code = 1
            return f"rm: cannot remove '{raw_target}': Is a directory"

        self._remove_subtree(target)
        self.last_exit_code = 0
        return ""

    def _handle_whoami(self, args: list[str]) -> str:
        if args:
            self.last_exit_code = 1
            return "whoami: extra operand"
        self.last_exit_code = 0
        return self.env["USER"]

    _CHMOD_FLAGS = {"R", "v", "c", "f"}
    _CHMOD_MODE_LETTERS = {"r", "w", "x", "u", "g", "o", "a", "s"}

    def _handle_chmod(self, args: list[str]) -> str:
        if not args:
            self.last_exit_code = 1
            return "chmod: missing operand"

        recursive = False
        mode_spec: str | None = None
        targets_raw: list[str] = []

        for arg in args:
            if mode_spec is None and arg.startswith("-") and arg != "-":
                rest = arg[1:]
                if len(rest) == 1 and rest in self._CHMOD_FLAGS:
                    for flag in rest:
                        if flag == "R" or flag == "r":
                            recursive = True
                            continue
                        self.last_exit_code = 1
                        return f"chmod: invalid option -- '{arg}'"
                elif len(rest) == 1 and rest in self._CHMOD_MODE_LETTERS:
                    mode_spec = arg
                elif any(c in arg for c in "+-="):
                    mode_spec = arg
                else:
                    for flag in rest:
                        if flag == "R" or flag == "r":
                            recursive = True
                            continue
                        self.last_exit_code = 1
                        return f"chmod: invalid option -- '{arg}'"
            elif mode_spec is None:
                mode_spec = arg
            else:
                targets_raw.append(arg)

        if mode_spec is None:
            self.last_exit_code = 1
            return "chmod: missing operand"
        if not targets_raw:
            self.last_exit_code = 1
            return "chmod: missing operand"

        parsed = self._parse_chmod_mode(mode_spec)
        if parsed is None:
            self.last_exit_code = 1
            return f"chmod: invalid mode: '{mode_spec}'"

        delta, set_mask, clear_mask = parsed

        for raw_target in targets_raw:
            target = self._resolve_path(raw_target)
            node = self._nodes.get(target)
            if node is None:
                self.last_exit_code = 1
                return f"chmod: cannot access '{raw_target}': No such file or directory"
            if recursive and node.is_dir:
                self._chmod_recursive(target, delta, set_mask, clear_mask)
            else:
                self._apply_chmod(node, delta, set_mask, clear_mask)

        self.last_exit_code = 0
        return ""

    def _parse_chmod_mode(self, spec: str):
        if spec.isdigit() and len(spec) in (3, 4):
            try:
                return ("=", int(spec, 8), 0)
            except ValueError:
                return None
        delta = None
        if "+" in spec:
            delta = "+"
            parts = spec.split("+", 1)
        elif "-" in spec:
            delta = "-"
            parts = spec.split("-", 1)
        elif "=" in spec:
            delta = "="
            parts = spec.split("=", 1)
        else:
            return None
        who_str = parts[0] or "a"
        perm_str = parts[1]
        who = 0
        if "u" in who_str:
            who |= 0o700
        if "g" in who_str:
            who |= 0o070
        if "o" in who_str:
            who |= 0o007
        if "a" in who_str or who == 0:
            who = 0o777
        perm = 0
        if "r" in perm_str:
            perm |= 0o444
        if "w" in perm_str:
            perm |= 0o222
        if "x" in perm_str:
            perm |= 0o111
        if "s" in perm_str:
            perm |= 0o4000
        return (delta, who & perm, who & perm)

    def _chmod_recursive(self, path: str, delta: str, set_mask: int, clear_mask: int) -> None:
        node = self._nodes.get(path)
        if node:
            self._apply_chmod(node, delta, set_mask, clear_mask)
        if node and node.is_dir:
            for child in self._children.get(path, set()):
                self._chmod_recursive(self._join(path, child), delta, set_mask, clear_mask)

    @staticmethod
    def _apply_chmod(node: _VfsNode, delta: str, set_mask: int, clear_mask: int) -> None:
        if delta == "+":
            node.mode |= set_mask
        elif delta == "-":
            node.mode &= ~clear_mask
        elif delta == "=":
            node.mode = set_mask

    # --- helpers ---------------------------------------------------------
    def _resolve_path(self, path: str) -> str:
        if path == "~" or path.startswith("~/"):
            path = self.env.get("HOME", "/root") + path[1:]
        base = path if path.startswith("/") else posixpath.join(self.cwd, path)
        normalized = posixpath.normpath(base)
        return normalized if normalized.startswith("/") else f"/{normalized}"

    def _substitute_vars(self, value: str) -> str:
        def replace(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(2) or ""
            return self.env.get(name, "")

        return _VAR_PATTERN.sub(replace, value)

    @staticmethod
    def _is_valid_var_name(name: str) -> bool:
        return (
            bool(name)
            and (name[0].isalpha() or name[0] == "_")
            and all(ch.isalnum() or ch == "_" for ch in name)
        )

    def _add_dir(self, path: str) -> None:
        parent, name = self._split(path)
        self._nodes[path] = _VfsNode("dir", 0o755)
        self._children.setdefault(path, set())
        if path != "/":
            self._children.setdefault(parent, set()).add(name)

    def _add_file(self, path: str) -> None:
        parent, name = self._split(path)
        self._nodes[path] = _VfsNode("file", 0o644)
        self._children.setdefault(parent, set()).add(name)

    def _list_children(self, path: str) -> list[str]:
        return sorted(self._children.get(path, set()))

    def _remove_subtree(self, path: str) -> None:
        node = self._nodes[path]
        if node.is_dir:
            for child in list(self._children.get(path, set())):
                self._remove_subtree(self._join(path, child))
            self._children.pop(path, None)

        parent, name = self._split(path)
        if path != "/":
            self._children.get(parent, set()).discard(name)
        self._nodes.pop(path, None)

    def _is_ancestor(self, candidate: str, path: str) -> bool:
        if candidate == path:
            return True
        if candidate == "/":
            return True
        return path.startswith(candidate + "/")

    @staticmethod
    def _join(parent: str, name: str) -> str:
        return "/" + name if parent == "/" else f"{parent}/{name}"

    @staticmethod
    def _split(abspath: str) -> tuple[str, str]:
        if abspath == "/":
            return "/", ""
        parent, name = posixpath.split(abspath)
        return parent or "/", name
