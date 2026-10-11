"""Small, strict project configuration shared by the CLI and composite Action."""
from __future__ import annotations

import json
import re
from pathlib import Path

from docker.errors import DockerException
from docker.utils import parse_bytes

CONFIG_NAME = ".opsscript-gate.json"
PRESETS = {
    "minimal": ["debian:12-slim", "alpine:3.20"],
    "ubuntu": ["ubuntu:22.04", "ubuntu:24.04"],
}
DEFAULTS = {
    "matrix": None, "preset": None, "jobs": None, "timeout": 60,
    "shell": "posix", "mem_limit": "256m", "pids_limit": 128,
    "network": "bridge", "packages": [], "exclude": [], "max_scripts": 20,
    "repeat": 1,
}

MAX_CONFIG_SIZE_BYTES = 256 * 1024
MAX_REPEAT_ATTEMPTS = 20
MAX_TIMEOUT_SECONDS = 3600
MAX_MATRIX_IMAGES = 32

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:-]*$")


def validate_memory_limit(value: object) -> str:
    """Reject invalid or unlimited Docker memory settings before execution."""
    message = "mem_limit must be a positive Docker memory limit (for example, 256m)"
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    normalized = value.strip()
    try:
        if parse_bytes(normalized) <= 0:
            raise ValueError(message)
    except (DockerException, OverflowError, ValueError) as exc:
        raise ValueError(message) from exc
    return normalized


def validate_packages(value: object) -> list[str]:
    """Validate and normalize package names used for optional container setup."""
    if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        raise ValueError("packages must be a list of package names")
    packages: list[str] = []
    for package in value:
        name = package.strip()
        if not name or not PACKAGE_NAME_RE.fullmatch(name):
            raise ValueError(
                "packages must contain nonempty package names using only letters, numbers, '+', '.', '_', ':', or '-'")
        if name not in packages:
            packages.append(name)
    return packages


def load_config(filename: str | None) -> dict:
    path = Path(filename or CONFIG_NAME)
    if filename is None and not path.exists():
        return {}
    try:
        # Read one byte beyond the limit so a concurrent file replacement or growth
        # cannot bypass the stat-based size check and force an unbounded allocation.
        with path.open("rb") as stream:
            raw_config = stream.read(MAX_CONFIG_SIZE_BYTES + 1)
        if len(raw_config) > MAX_CONFIG_SIZE_BYTES:
            raise ValueError(
                f"configuration exceeds {MAX_CONFIG_SIZE_BYTES // 1024} KiB limit"
            )
        config = json.loads(raw_config.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("Project configuration must be a JSON object")
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    for key, value in config.items():
        if key in {"jobs", "timeout", "pids_limit", "max_scripts", "repeat"}:
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
            if key == "repeat" and value > MAX_REPEAT_ATTEMPTS:
                raise ValueError(f"repeat must not exceed {MAX_REPEAT_ATTEMPTS}")
            if key == "timeout" and value > MAX_TIMEOUT_SECONDS:
                raise ValueError(f"timeout must not exceed {MAX_TIMEOUT_SECONDS} seconds")
        elif key == "exclude":
            if not isinstance(value, list) or not all(isinstance(p, str) and p for p in value):
                raise ValueError("exclude must be a list of nonempty glob strings")
        elif key == "packages":
            validate_packages(value)
        elif key == "mem_limit":
            validate_memory_limit(value)
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a nonempty string")
    for key, choices in {"shell": ("posix", "auto", "shebang"),
                         "network": ("bridge", "none"), "preset": PRESETS}.items():
        if key in config and config[key] not in choices:
            raise ValueError(f"Invalid {key}: {config[key]}")
    if "matrix" in config and "preset" in config:
        raise ValueError("Configure either matrix or preset, not both")
    if "matrix" in config:
        images = [image.strip() for image in config["matrix"].split(",") if image.strip()]
        if not images:
            raise ValueError("matrix must contain at least one image")
        if len(images) > MAX_MATRIX_IMAGES:
            raise ValueError(f"matrix must not contain more than {MAX_MATRIX_IMAGES} images")
    return config


def init_project() -> list[str]:
    """Create configuration and workflow without overwriting existing files."""
    files = {
        Path(CONFIG_NAME): json.dumps({"preset": "minimal", "shell": "auto",
            "network": "none", "exclude": ["tests/*", "examples/*"], "max_scripts": 20}, indent=2) + "\n",
        Path(".github/workflows/opsscript-gate.yml"): """name: Shell runtime compatibility
on: [push, pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  compatibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: Mresyzz/opsscript-gate@v0.9.4
        with:
          config: .opsscript-gate.json
""",
    }
    for path in files:
        if path.exists() or path.is_symlink():
            raise ValueError(f"Refusing to overwrite {path}; keep or rename it before init")
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return [str(path) for path in files]
