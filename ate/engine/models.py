from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


class StepStatus:
    PENDING = "Pending"
    RUNNING = "Running"
    PASSED = "Passed"
    FAILED = "Failed"


class RunStatus:
    TESTING = "TESTING"
    PASS = "PASS"
    FAIL = "FAIL"
    ABORTED = "ABORTED"


class EngineError(RuntimeError):
    pass


class StepFailure(EngineError):
    def __init__(self, message: str, measured: str = "") -> None:
        super().__init__(message)
        self.measured = measured  # valor ya formateado como str para mostrarlo directamente en la tabla de la UI


class OperatorAbort(EngineError):
    pass


@dataclass
class ProgramMetadata:
    name: str = "TP no cargado"
    version: str = "0.0"
    path: str = ""
    raw: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    station_id: str
    operator_name: str
    uut_serial: str


@dataclass
class TestStep:
    line: int
    name: str
    command: str
    arg1: str = ""
    arg2: str = ""
    arg3: str = ""
    arg4: str = ""
    low: str = ""
    high: str = ""
    unit: str = ""


@dataclass
class CommandResult:
    status: str = StepStatus.PASSED
    measured: Any = ""
    jump_to: int | None = None
    stop_program: bool = False
    message: str = ""


@dataclass
class RunResult:
    overall_status: str
    started_at: float
    finished_at: float
    registers: Dict[str, Any]
