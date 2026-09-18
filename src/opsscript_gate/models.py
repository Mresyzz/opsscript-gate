from dataclasses import dataclass, field
from enum import Enum


class DistroStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

@dataclass
class SingleResult:
    image: str
    status: DistroStatus
    exit_code: int | None
    stdout: str
    stderr: str
    execution_time: float

@dataclass
class RunReport:
    script_path: str
    results: list[SingleResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.status == DistroStatus.PASS for r in self.results)
