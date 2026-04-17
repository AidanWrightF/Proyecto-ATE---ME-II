from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
from pathlib import Path
import time
from typing import Any, Callable, Dict, Optional

from instruments import InstrumentBundle, InstrumentConfig, InstrumentError, open_instruments


EventCallback = Callable[[dict], None]
PromptHandler = Callable[[str], bool]


class EngineError(RuntimeError):
    pass


class StepFailure(EngineError):
    pass


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
    status: str = "Passed"
    measured: Any = ""
    jump_to: Optional[int] = None
    stop_program: bool = False
    message: str = ""


@dataclass
class RunResult:
    overall_status: str
    started_at: float
    finished_at: float
    registers: Dict[str, Any]


def load_test_program(path: str | Path) -> tuple[ProgramMetadata, list[TestStep]]:
    path = Path(path)
    metadata: Dict[str, str] = {}
    csv_lines: list[str] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                key, value = _parse_metadata_line(stripped)
                if key:
                    metadata[key] = value
                continue
            csv_lines.append(raw_line)

    if not csv_lines:
        raise EngineError(f"El archivo TP esta vacio: {path}")

    reader = csv.DictReader(io.StringIO("".join(csv_lines)))
    required = {"line", "name", "command", "arg1", "arg2", "arg3", "arg4", "low", "high", "unit"}
    if not reader.fieldnames or set(reader.fieldnames) != required:
        raise EngineError(
            "El TP debe tener las columnas exactas: "
            "line,name,command,arg1,arg2,arg3,arg4,low,high,unit"
        )

    steps: list[TestStep] = []
    for row in reader:
        if not row:
            continue
        line_value = (row.get("line") or "").strip()
        if not line_value:
            continue
        steps.append(
            TestStep(
                line=int(line_value),
                name=(row.get("name") or "").strip(),
                command=(row.get("command") or "").strip().upper(),
                arg1=(row.get("arg1") or "").strip(),
                arg2=(row.get("arg2") or "").strip(),
                arg3=(row.get("arg3") or "").strip(),
                arg4=(row.get("arg4") or "").strip(),
                low=(row.get("low") or "").strip(),
                high=(row.get("high") or "").strip(),
                unit=(row.get("unit") or "").strip(),
            )
        )

    steps.sort(key=lambda item: item.line)
    line_numbers = [step.line for step in steps]
    if len(line_numbers) != len(set(line_numbers)):
        raise EngineError("El TP contiene numeros de linea duplicados.")

    return (
        ProgramMetadata(
            name=metadata.get("TP_NAME", path.stem),
            version=metadata.get("TP_VERSION", "1.0"),
            path=str(path),
            raw=metadata,
        ),
        steps,
    )


def _parse_metadata_line(line: str) -> tuple[str, str]:
    content = line[1:].strip()
    if ":" not in content:
        return "", ""
    key, value = content.split(":", 1)
    return key.strip().upper(), value.strip()


class TestExecutiveEngine:
    def __init__(
        self,
        event_callback: Optional[EventCallback] = None,
        prompt_handler: Optional[PromptHandler] = None,
    ) -> None:
        self.event_callback = event_callback or (lambda event: None)
        self.prompt_handler = prompt_handler or (lambda message: True)
        self.metadata = ProgramMetadata()
        self.program: list[TestStep] = []
        self._line_index: Dict[int, int] = {}
        self.registers: Dict[str, Any] = {}
        self._paused = False
        self._stop_requested = False
        self._dispatch = {
            "RESET": self._cmd_reset,
            "LOAD": self._cmd_load,
            "SUM": self._cmd_sum,
            "COMP": self._cmd_comp,
            "IF": self._cmd_if,
            "JMP": self._cmd_jmp,
            "TXT": self._cmd_txt,
            "WAIT": self._cmd_wait,
            "DDS_SQUARE": self._cmd_dds_square,
            "GEN_OUTPUT": self._cmd_gen_output,
            "OSC_AUTOSCALE": self._cmd_osc_autoscale,
            "OSC_MEASURE": self._cmd_osc_measure,
            "LOG": self._cmd_log,
            "END": self._cmd_end,
        }

    def load_program(self, path: str | Path) -> ProgramMetadata:
        self.metadata, self.program = load_test_program(path)
        self._line_index = {step.line: index for index, step in enumerate(self.program)}
        self.emit(
            {
                "type": "program_loaded",
                "metadata": {
                    "name": self.metadata.name,
                    "version": self.metadata.version,
                    "path": self.metadata.path,
                },
            }
        )
        return self.metadata

    def request_stop(self) -> None:
        self._stop_requested = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.emit({"type": "paused", "paused": paused})

    def run(
        self,
        context: ExecutionContext,
        instrument_config: Optional[InstrumentConfig] = None,
    ) -> RunResult:
        if not self.program:
            raise EngineError("No hay ningun TP cargado.")

        started_at = time.time()
        self.registers = {}
        self._paused = False
        self._stop_requested = False
        bundle: Optional[InstrumentBundle] = None
        overall_status = "FAIL"
        self.emit(
            {
                "type": "run_started",
                "context": {
                    "station_id": context.station_id,
                    "operator_name": context.operator_name,
                    "uut_serial": context.uut_serial,
                },
                "metadata": {
                    "name": self.metadata.name,
                    "version": self.metadata.version,
                },
            }
        )
        self.emit({"type": "status", "value": "TESTING"})
        self.log(
            f"Inicio de prueba. TP={self.metadata.name} v{self.metadata.version} "
            f"| Estacion={context.station_id} | Operario={context.operator_name} | UUT={context.uut_serial or 'N/A'}"
        )

        try:
            bundle = open_instruments(instrument_config)
            self.log(f"Modo de instrumentos: {'MOCK' if bundle.mock_mode else 'REAL'}")
            self.log(f"Osciloscopio: {bundle.scope.identify()}")
            self.log(f"Generador: {bundle.generator.identify()}")

            ip = 0
            while ip < len(self.program):
                self._check_runtime_flags()
                step = self.program[ip]
                started_step = time.perf_counter()
                self.emit(self._step_event(step, "Running", "", "", "", ""))

                try:
                    result = self._execute_step(step, bundle, context)
                except StepFailure as exc:
                    duration_s = time.perf_counter() - started_step
                    self.emit(
                        self._step_event(
                            step,
                            "Failed",
                            getattr(exc, "measured", ""),
                            self._format_bound(step.low),
                            self._format_bound(step.high),
                            self._format_duration(duration_s),
                        )
                    )
                    self.log(str(exc), level="ERROR")
                    raise
                except OperatorAbort as exc:
                    duration_s = time.perf_counter() - started_step
                    self.emit(
                        self._step_event(
                            step,
                            "Failed",
                            "",
                            self._format_bound(step.low),
                            self._format_bound(step.high),
                            self._format_duration(duration_s),
                        )
                    )
                    self.log(str(exc), level="ERROR")
                    raise
                except Exception as exc:
                    duration_s = time.perf_counter() - started_step
                    self.emit(
                        self._step_event(
                            step,
                            "Failed",
                            "",
                            self._format_bound(step.low),
                            self._format_bound(step.high),
                            self._format_duration(duration_s),
                        )
                    )
                    self.log(
                        f"Error inesperado en paso {step.line} ({step.command}): "
                        f"{type(exc).__name__}: {exc}",
                        level="ERROR",
                    )
                    raise

                duration_s = time.perf_counter() - started_step
                self.emit(
                    self._step_event(
                        step,
                        result.status,
                        self._format_measured(result.measured),
                        self._format_bound(step.low),
                        self._format_bound(step.high),
                        self._format_duration(duration_s),
                    )
                )

                if result.message:
                    self.log(result.message)
                if result.stop_program:
                    break
                if result.jump_to is not None:
                    ip = self._resolve_jump(result.jump_to)
                else:
                    ip += 1

            overall_status = "PASS"
            self.emit({"type": "status", "value": "PASS"})
            self.log("Prueba finalizada con resultado PASS.")
        except StepFailure:
            overall_status = "FAIL"
            self.emit({"type": "status", "value": "FAIL"})
            self.log("Prueba finalizada con resultado FAIL.", level="ERROR")
        except OperatorAbort:
            overall_status = "ABORTED"
            self.emit({"type": "status", "value": "ABORTED"})
            self.log("Prueba abortada por el operador.", level="ERROR")
        except (InstrumentError, EngineError, ValueError) as exc:
            overall_status = "FAIL"
            self.emit({"type": "status", "value": "FAIL"})
            self.log(f"Error de ejecucion: {exc}", level="ERROR")
        except Exception as exc:
            overall_status = "FAIL"
            self.emit({"type": "status", "value": "FAIL"})
            self.log(
                f"Error inesperado de ejecucion ({type(exc).__name__}): {exc}",
                level="ERROR",
            )
        finally:
            if bundle is not None:
                try:
                    bundle.generator.output(False)
                except Exception:
                    pass
                try:
                    bundle.close()
                except Exception as exc:
                    self.log(f"Advertencia al cerrar instrumentos: {exc}", level="ERROR")

        finished_at = time.time()
        result = RunResult(
            overall_status=overall_status,
            started_at=started_at,
            finished_at=finished_at,
            registers=dict(self.registers),
        )
        self.emit(
            {
                "type": "run_complete",
                "overall_status": overall_status,
                "duration_s": round(finished_at - started_at, 3),
                "registers": dict(self.registers),
            }
        )
        return result

    def emit(self, event: dict) -> None:
        self.event_callback(event)

    def log(self, message: str, level: str = "INFO") -> None:
        self.emit(
            {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": time.strftime("%H:%M:%S"),
            }
        )

    def _execute_step(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        if step.command not in self._dispatch:
            raise EngineError(f"Instruccion no soportada: {step.command}")
        return self._dispatch[step.command](step, bundle, context)

    def _step_event(
        self,
        step: TestStep,
        status: str,
        measured: str,
        low: str,
        high: str,
        duration: str,
    ) -> dict:
        return {
            "type": "step",
            "line": step.line,
            "name": step.name,
            "status": status,
            "measured": measured,
            "low": low,
            "high": high,
            "unit": step.unit,
            "duration": duration,
        }

    def _check_runtime_flags(self) -> None:
        while self._paused:
            if self._stop_requested:
                raise OperatorAbort("Se recibio ABORT mientras la prueba estaba en pausa.")
            time.sleep(0.1)
        if self._stop_requested:
            raise OperatorAbort("Se recibio ABORT por parte del operador.")

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
            failure = StepFailure(
                f"{step.name}: valor {value:.6g} {step.unit} por debajo del limite inferior {float(low):.6g} {step.unit}"
            )
            failure.measured = self._format_measured(value)
            raise failure
        if high is not None and value > float(high):
            failure = StepFailure(
                f"{step.name}: valor {value:.6g} {step.unit} por encima del limite superior {float(high):.6g} {step.unit}"
            )
            failure.measured = self._format_measured(value)
            raise failure

    def _cmd_reset(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del step, context
        self.registers = {}
        bundle.generator.reset()
        bundle.scope.reset()
        return CommandResult(message="Instrumentos y registros reiniciados.")

    def _cmd_load(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        if not step.arg1:
            raise EngineError("LOAD requiere arg1 como nombre de registro.")
        value = self._resolve_value(step.arg2)
        self.registers[step.arg1] = value
        return CommandResult(message=f"Registro {step.arg1} = {value}")

    def _cmd_sum(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        if not step.arg3:
            raise EngineError("SUM requiere arg3 como registro destino.")
        result = float(self._resolve_value(step.arg1)) + float(self._resolve_value(step.arg2))
        self.registers[step.arg3] = result
        return CommandResult(measured=result, message=f"{step.arg3} = {result:.6g}")

    def _cmd_comp(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        if not step.arg3:
            raise EngineError("COMP requiere arg3 como registro destino.")
        result = float(self._resolve_value(step.arg1)) - float(self._resolve_value(step.arg2))
        self.registers[step.arg3] = result
        return CommandResult(measured=result, message=f"{step.arg3} = {result:.6g}")

    def _cmd_if(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        left = self._resolve_value(step.arg1)
        operator = step.arg2.strip()
        right = self._resolve_value(step.arg3)
        target = int(self._resolve_value(step.arg4))

        operations = {
            "==": left == right,
            "!=": left != right,
            ">": left > right,
            "<": left < right,
            ">=": left >= right,
            "<=": left <= right,
        }
        if operator not in operations:
            raise EngineError(f"Operador IF no soportado: {operator}")
        if operations[operator]:
            return CommandResult(jump_to=target, message=f"IF verdadero. Salto a linea {target}.")
        return CommandResult(message="IF falso. Continua secuencia.")

    def _cmd_jmp(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        target = int(self._resolve_value(step.arg1))
        return CommandResult(jump_to=target, message=f"Salto incondicional a linea {target}.")

    def _cmd_txt(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        message = step.arg1 or step.name or "Confirme para continuar."
        accepted = self.prompt_handler(message)
        if not accepted:
            raise OperatorAbort("El operador cancelo la instruccion manual.")
        return CommandResult(message=f"Operador confirmo: {message}")

    def _cmd_wait(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        seconds = float(self._resolve_value(step.arg1) or 0.0)
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            self._check_runtime_flags()
            time.sleep(0.05)
        return CommandResult(message=f"Espera completada: {seconds:.3f} s")

    def _cmd_dds_square(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del context
        frequency_hz = float(self._resolve_value(step.arg1))
        amplitude_vpp = float(self._resolve_value(step.arg2))
        offset_v = float(self._resolve_value(step.arg3) or 0.0)
        duty_cycle = float(self._resolve_value(step.arg4) or 50.0)
        bundle.generator.set_square(frequency_hz, amplitude_vpp, offset_v, duty_cycle)
        return CommandResult(
            message=(
                f"DDS configurado: square {frequency_hz:.6g} Hz, "
                f"{amplitude_vpp:.6g} Vpp, offset {offset_v:.6g} V, duty {duty_cycle:.3g}%"
            )
        )

    def _cmd_gen_output(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del context
        enabled = bool(self._resolve_value(step.arg1))
        bundle.generator.output(enabled)
        return CommandResult(message=f"Salida del generador {'ON' if enabled else 'OFF'}.")

    def _cmd_osc_autoscale(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del step, context
        bundle.scope.autoscale()
        return CommandResult(message="Osciloscopio en autoscale.")

    def _cmd_osc_measure(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del context
        measurement = step.arg1 or "VPP"
        channel = step.arg2 or "CHAN1"
        register_name = step.arg3 or f"REG_{measurement}"
        value = float(bundle.scope.measure(measurement, channel))
        self.registers[register_name] = value
        self._assert_in_range(value, step)
        return CommandResult(
            measured=value,
            message=f"{measurement} en {channel}: {value:.6g} {step.unit}".strip(),
        )

    def _cmd_log(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del bundle, context
        return CommandResult(message=step.arg1 or step.name)

    def _cmd_end(
        self,
        step: TestStep,
        bundle: InstrumentBundle,
        context: ExecutionContext,
    ) -> CommandResult:
        del step, bundle, context
        return CommandResult(stop_program=True, message="Fin de programa.")
