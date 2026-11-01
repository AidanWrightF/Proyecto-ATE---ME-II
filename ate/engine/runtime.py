from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from ..instruments import InstrumentBundle, InstrumentError, open_instruments

from .commands import COMMAND_DISPATCH
from .loader import load_test_program
from .models import (
    CommandResult,
    EngineError,
    OperatorAbort,
    ProgramMetadata,
    RunResult,
    RunStatus,
    StepFailure,
    StepRecord,
    StepStatus,
    TestStep,
)


EventCallback = Callable[[dict], None]
PromptHandler = Callable[[str], bool]

logger = logging.getLogger("ate")


class TestExecutiveEngine:
    def __init__(
        self,
        event_callback: EventCallback | None = None,
        prompt_handler: PromptHandler | None = None,
    ) -> None:
        self.event_callback = event_callback or (lambda event: None)
        self.prompt_handler = prompt_handler or (lambda message: True)
        self.metadata = ProgramMetadata()
        self.program: list[TestStep] = []
        self._line_index: dict[int, int] = {}  # mapea número de línea del TP a índice en `program` para saltos JMP/IF en O(1)
        self.registers: dict[str, Any] = {}
        self._dispatch = dict(COMMAND_DISPATCH)

    def load_program(self, path: str | Path) -> ProgramMetadata:
        self.metadata, self.program = load_test_program(path)
        self._line_index = {step.line: index for index, step in enumerate(self.program)}
        return self.metadata

    def run(self) -> RunResult:
        if not self.program:
            raise EngineError("No hay ningun TP cargado.")

        started_at = time.time()
        self.registers = {}
        records: list[StepRecord] = []
        bundle: InstrumentBundle | None = None
        overall_status = RunStatus.FAIL
        total = len(self.program)

        self.log(f"Inicio de prueba. TP={self.metadata.name} v{self.metadata.version}")
        self.emit({"type": "progress", "current": 0, "total": total})

        try:
            bundle = open_instruments()
            self.log(f"Osciloscopio: {bundle.scope.identify()}")

            ip = 0
            while ip < total:
                step = self.program[ip]
                started_step = time.perf_counter()

                try:
                    step_result = self._execute_step(step, bundle)
                except StepFailure as exc:
                    records.append(self._record(step, StepStatus.FAILED, exc.measured, time.perf_counter() - started_step))
                    self.log(str(exc), level="ERROR")
                    raise
                except OperatorAbort as exc:
                    records.append(self._record(step, StepStatus.FAILED, "", time.perf_counter() - started_step))
                    self.log(str(exc), level="ERROR")
                    raise
                except Exception as exc:
                    records.append(self._record(step, StepStatus.FAILED, "", time.perf_counter() - started_step))
                    self.log(
                        f"Error inesperado en paso {step.line} ({step.command}): "
                        f"{type(exc).__name__}: {exc}",
                        level="ERROR",
                    )
                    raise

                duration_s = time.perf_counter() - started_step
                records.append(
                    self._record(step, step_result.status, self._format_measured(step_result.measured), duration_s)
                )

                if step_result.message:
                    self.log(step_result.message)
                if step_result.stop_program:
                    break
                if step_result.jump_to is not None:
                    ip = self._resolve_jump(step_result.jump_to)
                else:
                    ip += 1
                self.emit({"type": "progress", "current": ip, "total": total})

            overall_status = RunStatus.PASS
            self.log("Prueba finalizada con resultado PASS.")
        except StepFailure:
            overall_status = RunStatus.FAIL
            self.log("Prueba finalizada con resultado FAIL.", level="ERROR")
        except OperatorAbort:
            overall_status = RunStatus.ABORTED
            self.log("Prueba abortada por el operador.", level="ERROR")
        except (InstrumentError, EngineError, ValueError) as exc:
            overall_status = RunStatus.FAIL
            self.log(f"Error de ejecucion: {exc}", level="ERROR")
        except Exception as exc:
            overall_status = RunStatus.FAIL
            self.log(f"Error inesperado de ejecucion ({type(exc).__name__}): {exc}", level="ERROR")
        finally:
            if bundle is not None:
                try:
                    bundle.close()
                except Exception as exc:
                    self.log(f"Advertencia al cerrar instrumentos: {exc}", level="ERROR")

        finished_at = time.time()
        self.emit({"type": "progress", "current": total, "total": total})
        return RunResult(
            overall_status=overall_status,
            started_at=started_at,
            finished_at=finished_at,
            registers=dict(self.registers),
            steps=records,
        )

    def emit(self, event: dict) -> None:
        self.event_callback(event)

    def log(self, message: str, level: str = "INFO") -> None:
        # El log va a la consola (el operario no la ve); nunca a la UI.
        if level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

    def _execute_step(self, step: TestStep, bundle: InstrumentBundle) -> CommandResult:
        if step.command not in self._dispatch:
            raise EngineError(f"Instruccion no soportada: {step.command}")
        return self._dispatch[step.command](self, step, bundle)

    def _record(self, step: TestStep, status: str, measured: str, duration_s: float) -> StepRecord:
        return StepRecord(
            line=step.line,
            name=step.name,
            command=step.command,
            measured=measured,
            low=self._format_bound(step.low),
            high=self._format_bound(step.high),
            unit=step.unit,
            status=status,
            duration=self._format_duration(duration_s),
        )

    def _resolve_jump(self, target_line: int) -> int:
        if target_line not in self._line_index:
            raise EngineError(f"Linea de salto inexistente: {target_line}")
        return self._line_index[target_line]

    def _resolve_value(self, token: str) -> Any:
        token = (token or "").strip()
        if token == "":
            return None
        if token in self.registers:
            return self.registers[token]
        upper = token.upper()
        if upper in {"ON", "TRUE", "YES"}:
            return True
        if upper in {"OFF", "FALSE", "NO"}:
            return False
        try:
            # Heurística: si el token contiene '.', 'e' o 'E' se asume float; de lo contrario int; si falla, se retorna como str.
            if any(mark in token for mark in (".", "e", "E")):
                return float(token)
            return int(token)
        except ValueError:
            return token

    def _format_measured(self, value: Any) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            return f"{value:.6g}"
        return str(value)

    def _format_bound(self, raw: str) -> str:
        value = self._resolve_value(raw) if raw else None
        return self._format_measured(value)

    @staticmethod
    def _format_duration(duration_s: float) -> str:
        return f"{duration_s:.3f}"

    def _assert_in_range(self, value: float, step: TestStep) -> None:
        low = self._resolve_value(step.low) if step.low else None
        high = self._resolve_value(step.high) if step.high else None
        if low is not None and value < float(low):
            raise StepFailure(
                f"{step.name}: valor {value:.6g} {step.unit} por debajo del limite inferior {float(low):.6g} {step.unit}",
                measured=self._format_measured(value),
            )
        if high is not None and value > float(high):
            raise StepFailure(
                f"{step.name}: valor {value:.6g} {step.unit} por encima del limite superior {float(high):.6g} {step.unit}",
                measured=self._format_measured(value),
            )
