from __future__ import annotations

import os
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


def is_shell_script(file_path: Path, max_size_bytes: int = MAX_SCRIPT_SIZE_BYTES) -> bool:
    """
    Check if a file is a candidate shell script:
    - Must be a regular file and not a symlink to an invalid target.
    - File size must not exceed max_size_bytes.
    - Extension is .sh or .bash, OR the first line is a recognized shell shebang.
    """
    try:
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
        return any(first_line.startswith(prefix) for prefix in SHELL_SHEBANG_PREFIXES)
    except (OSError, PermissionError):
        return False


def discover_scripts(
    root_dir: str = ".",
    max_scripts: int = MAX_DISCOVERED_SCRIPTS,
    max_size_bytes: int = MAX_SCRIPT_SIZE_BYTES,
) -> list[str]:
    """
    Discover candidate shell scripts within root_dir, respecting ignored directories
    and caps on file count and size.

    Returns normalized relative POSIX paths sorted alphabetically for deterministic ordering.
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
                    # Prepend ./ if top-level for standard script path conventions
                    if not rel_path.startswith("./") and "/" not in rel_path:
                        rel_path = f"./{rel_path}"
                    discovered.append(rel_path)
                except ValueError:
                    discovered.append(str(file_path))

    # Sort alphabetically for stable, deterministic ordering
    discovered.sort()
    return discovered[:max_scripts]
