"""Small, strict project configuration shared by the CLI and composite Action."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_NAME = ".opsscript-gate.json"
PRESETS = {
    "minimal": ["debian:12-slim", "alpine:3.20"],
    "ubuntu": ["ubuntu:22.04", "ubuntu:24.04"],
}
DEFAULTS = {
    "matrix": None, "preset": None, "jobs": None, "timeout": 60,
    "shell": "posix", "mem_limit": "256m", "pids_limit": 128,
    "network": "bridge", "exclude": [], "max_scripts": 20,
}


def load_config(filename: str | None) -> dict:
    path = Path(filename or CONFIG_NAME)
    if filename is None and not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("Project configuration must be a JSON object")
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    for key, value in config.items():
        if key in {"jobs", "timeout", "pids_limit", "max_scripts"}:
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        elif key == "exclude":
            if not isinstance(value, list) or not all(isinstance(p, str) and p for p in value):
                raise ValueError("exclude must be a list of nonempty glob strings")
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a nonempty string")
    for key, choices in {"shell": ("posix", "auto", "shebang"),
                         "network": ("bridge", "none"), "preset": PRESETS}.items():
        if key in config and config[key] not in choices:
            raise ValueError(f"Invalid {key}: {config[key]}")
    if "matrix" in config and "preset" in config:
        raise ValueError("Configure either matrix or preset, not both")
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
      - uses: Mresyzz/opsscript-gate@v0.5.0
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
