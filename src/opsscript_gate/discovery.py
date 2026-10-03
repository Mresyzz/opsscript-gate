from __future__ import annotations

import os
import fnmatch
import subprocess
from pathlib import Path

# Directories to ignore during automatic script discovery
IGNORED_DIRS = {
    ".git",
    ".github",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "vendor",
    "target",
    ".tox",
    ".nox",
    "dist",
    "build",
    ".pytest_cache",
    ".eggs",
}

# Recognized shell shebang prefixes for non-.sh executable discovery
SHELL_SHEBANG_PREFIXES = (
    "#!/bin/sh",
    "#!/bin/bash",
    "#!/usr/bin/sh",
    "#!/usr/bin/bash",
    "#!/usr/bin/env sh",
    "#!/usr/bin/env bash",
)

MAX_DISCOVERED_SCRIPTS = 20
MAX_SCRIPT_SIZE_BYTES = 1024 * 1024  # 1 MB


def _matches_exclude(rel_path: str, patterns: list[str] | None) -> bool:
    """Match exclusions consistently whether callers use ``foo.sh`` or ``./foo.sh``."""
    normalized_path = rel_path[2:] if rel_path.startswith("./") else rel_path
    for pattern in patterns or []:
        normalized_pattern = pattern[2:] if pattern.startswith("./") else pattern
        if fnmatch.fnmatchcase(normalized_path, normalized_pattern):
            return True
    return False


def is_shell_script(file_path: Path, max_size_bytes: int = MAX_SCRIPT_SIZE_BYTES) -> bool:
    """
    Check if a file is a candidate shell script:
    - Must be a regular file, never a symlink.
    - File size must not exceed max_size_bytes.
    - Extension is .sh or .bash, OR the first line is a recognized shell shebang.
    """
    try:
        if file_path.is_symlink() or not file_path.is_file():
            return False
        stat = file_path.stat()
        if stat.st_size == 0 or stat.st_size > max_size_bytes:
            return False

        ext = file_path.suffix.lower()
        if ext in (".sh", ".bash"):
            return True

        # If extension is not .sh/.bash, inspect the first line
        with open(file_path, "rb") as f:
            first_line_bytes = f.readline(256)

        first_line = first_line_bytes.decode("utf-8", errors="ignore").strip()
        return any(first_line == prefix or first_line.startswith(prefix + " ")
                   for prefix in SHELL_SHEBANG_PREFIXES)
    except (OSError, PermissionError):
        return False


def discover_scripts(
    root_dir: str = ".",
    max_scripts: int = MAX_DISCOVERED_SCRIPTS,
    max_size_bytes: int = MAX_SCRIPT_SIZE_BYTES,
    exclude: list[str] | None = None,
) -> list[str]:
    """
    Discover candidate shell scripts within root_dir, respecting ignored directories
    and caps on file count and size.

    Returns normalized relative POSIX paths sorted alphabetically for deterministic ordering.
    Raises ValueError on overflow so a successful gate never silently omits scripts.
    """
    root_path = Path(root_dir).resolve()
    discovered: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORED_DIRS
            and not d.endswith(".egg-info")
            and not d.startswith(".")
        ]

        current_path = Path(dirpath)

        for filename in filenames:
            file_path = current_path / filename
            if is_shell_script(file_path, max_size_bytes=max_size_bytes):
                try:
                    rel_path = file_path.relative_to(root_path).as_posix()
                    if _matches_exclude(rel_path, exclude):
                        continue
                    # Prepend ./ if top-level for standard script path conventions
                    if not rel_path.startswith("./") and "/" not in rel_path:
                        rel_path = f"./{rel_path}"
                    discovered.append(rel_path)
                except ValueError:
                    discovered.append(str(file_path))
                if len(discovered) > max_scripts:
                    raise ValueError(
                        f"Discovered more than {max_scripts} scripts, exceeding limit. "
                        "Use --exclude or increase --max-scripts; no scripts were executed."
                    )

    # Sort alphabetically for stable, deterministic ordering
    discovered.sort()
    return discovered


def discover_changed_scripts(
    root_dir: str = ".",
    since: str = "HEAD^",
    max_scripts: int = MAX_DISCOVERED_SCRIPTS,
    max_size_bytes: int = MAX_SCRIPT_SIZE_BYTES,
    exclude: list[str] | None = None,
) -> list[str]:
    """Discover shell scripts changed between ``since`` and ``HEAD``.

    Git provides the candidate paths; the same file, size, shebang, exclusion,
    and overflow checks used by normal discovery still apply. A missing Git
    repository or unavailable revision is reported as a user-facing error.
    """
    root_path = Path(root_dir).resolve()
    if not since or not since.strip() or since.startswith("-") or any(char.isspace() for char in since):
        raise ValueError("changed-since must name a Git revision")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "-z",
             f"{since}...HEAD", "--"],
            cwd=root_path,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ValueError("changed-since requires Git to be installed") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"Cannot compare Git revision {since!r} with HEAD"
            + (f": {detail}" if detail else "")
        ) from exc

    changed_paths = [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]
    discovered: list[str] = []
    for relative_name in changed_paths:
        candidate = root_path / Path(relative_name)
        try:
            resolved = candidate.resolve()
            rel_path = resolved.relative_to(root_path).as_posix()
        except (OSError, ValueError):
            continue
        if _matches_exclude(rel_path, exclude):
            continue
        if not is_shell_script(candidate, max_size_bytes=max_size_bytes):
            continue
        normalized = rel_path if "/" in rel_path else f"./{rel_path}"
        discovered.append(normalized)
        if len(discovered) > max_scripts:
            raise ValueError(
                f"Changed files include more than {max_scripts} shell scripts, exceeding limit. "
                "Use --exclude or increase --max-scripts; no scripts were executed."
            )

    return sorted(set(discovered))
