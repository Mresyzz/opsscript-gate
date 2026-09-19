from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DistroStatus(str, Enum):
    """Execution status for a specific Linux distribution."""
    PASS = "PASS"
    FAIL = "FAIL"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


class ShellMode(str, Enum):
    """Execution mode for shell scripts."""
    POSIX = "posix"
    SHEBANG = "shebang"
    AUTO = "auto"


@dataclass
class FailureDiagnostic:
    """Structured diagnostic information for execution failures."""
    kind: str
    message: str
    command: str | None = None
    line: int | None = None
    distro: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind,
            "message": self.message,
        }
        if self.command is not None:
            d["command"] = self.command
        if self.line is not None:
            d["line"] = self.line
        if self.distro is not None:
            d["distro"] = self.distro
        if self.hint is not None:
            d["hint"] = self.hint
        return d


@dataclass
class SingleResult:
    """Execution result for a single Linux distribution."""
    distro: str
    status: DistroStatus
    exit_code: int | None
    duration: float
    output_snippet: str = ""
    error_message: str | None = None
    diagnostic: FailureDiagnostic | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "distro": self.distro,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 3),
            "output_snippet": self.output_snippet,
            "error_message": self.error_message,
            "diagnostic": self.diagnostic.to_dict() if self.diagnostic is not None else None,
        }


@dataclass
class RunReport:
    """Consolidated report across all tested distributions."""
    results: list[SingleResult] = field(default_factory=list)
    total_duration: float = 0.0
    all_passed: bool = True

    def __post_init__(self) -> None:
        if self.results:
            self.all_passed = all(r.status == DistroStatus.PASS for r in self.results)
        else:
            self.all_passed = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total_duration": round(self.total_duration, 3),
            "all_passed": self.all_passed,
        }


@dataclass
class MultiScriptReport:
    """Consolidated report across multiple tested scripts."""
    reports: dict[str, RunReport] = field(default_factory=dict)
    total_duration: float = 0.0
    all_passed: bool = True

    def __post_init__(self) -> None:
        if self.reports:
            self.all_passed = all(r.all_passed for r in self.reports.values())
        else:
            self.all_passed = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "reports": {script: r.to_dict() for script, r in self.reports.items()},
            "total_duration": round(self.total_duration, 3),
            "all_passed": self.all_passed,
        }
