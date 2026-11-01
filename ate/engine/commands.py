from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..instruments import InstrumentBundle, InstrumentError

from .models import CommandResult, EngineError, OperatorAbort, TestStep

if TYPE_CHECKING:
    from .runtime import TestExecutiveEngine

# Valor que devuelve el RIGOL cuando la señal no es medible (fuera de rango).
_RIGOL_NO_VALUE = 9.9e37


def cmd_reset(
    engine: TestExecutiveEngine,
    _step: TestStep,
    bundle: InstrumentBundle,
) -> CommandResult:
    engine.registers = {}
    bundle.scope.reset()
    return CommandResult(message="Osciloscopio y registros reiniciados.")


def cmd_load(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    if not step.arg1:
        raise EngineError("LOAD requiere arg1 como nombre de registro.")
    value = engine._resolve_value(step.arg2)
    engine.registers[step.arg1] = value
    return CommandResult(message=f"Registro {step.arg1} = {value}")


def cmd_sum(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    if not step.arg3:
        raise EngineError("SUM requiere arg3 como registro destino.")
    result = float(engine._resolve_value(step.arg1)) + float(engine._resolve_value(step.arg2))
    engine.registers[step.arg3] = result
    return CommandResult(measured=result, message=f"{step.arg3} = {result:.6g}")


def cmd_comp(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    if not step.arg3:
        raise EngineError("COMP requiere arg3 como registro destino.")
    result = float(engine._resolve_value(step.arg1)) - float(engine._resolve_value(step.arg2))
    engine.registers[step.arg3] = result
    return CommandResult(measured=result, message=f"{step.arg3} = {result:.6g}")


def cmd_if(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    left = engine._resolve_value(step.arg1)
    operator = step.arg2.strip()
    right = engine._resolve_value(step.arg3)
    target = int(engine._resolve_value(step.arg4))

    try:
        operations = {
            "==": left == right,
            "!=": left != right,
            ">": float(left) > float(right),
            "<": float(left) < float(right),
            ">=": float(left) >= float(right),
            "<=": float(left) <= float(right),
        }
    except (TypeError, ValueError) as exc:
        raise EngineError(f"IF: no se pueden comparar '{left}' y '{right}': {exc}") from exc

    if operator not in operations:
        raise EngineError(f"Operador IF no soportado: {operator}")
    if operations[operator]:
        return CommandResult(jump_to=target, message=f"IF verdadero. Salto a linea {target}.")
    return CommandResult(message="IF falso. Continua secuencia.")


def cmd_jmp(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    target = int(engine._resolve_value(step.arg1))
    return CommandResult(jump_to=target, message=f"Salto incondicional a linea {target}.")


def cmd_txt(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    message = step.arg1 or step.name or "Confirme para continuar."
    accepted = engine.prompt_handler(message)
    if not accepted:
        raise OperatorAbort("El operador cancelo la instruccion manual.")
    return CommandResult(message=f"Operador confirmo: {message}")


def cmd_wait(
    engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    seconds = float(engine._resolve_value(step.arg1) or 0.0)
    time.sleep(seconds)
    return CommandResult(message=f"Espera completada: {seconds:.3f} s")


def cmd_osc_autoscale(
    _engine: TestExecutiveEngine,
    _step: TestStep,
    bundle: InstrumentBundle,
) -> CommandResult:
    bundle.scope.autoscale()
    return CommandResult(message="Osciloscopio en autoscale.")


def cmd_osc_measure(
    engine: TestExecutiveEngine,
    step: TestStep,
    bundle: InstrumentBundle,
) -> CommandResult:
    measurement = step.arg1 or "VPP"
    channel = step.arg2 or "CHAN1"
    register_name = step.arg3 or f"REG_{measurement}"

    value = bundle.scope.measure(measurement, channel)

    if value >= _RIGOL_NO_VALUE:
        raise InstrumentError(
            f"El osciloscopio no pudo medir {measurement} en {channel}: señal no disponible o fuera de rango."
        )

    engine.registers[register_name] = value
    engine._assert_in_range(value, step)
    return CommandResult(
        measured=value,
        message=f"{measurement} en {channel}: {value:.6g} {step.unit}".strip(),
    )


def cmd_log(
    _engine: TestExecutiveEngine,
    step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    return CommandResult(message=step.arg1 or step.name)


def cmd_osc_slope(
    _engine: TestExecutiveEngine,
    step: TestStep,
    bundle: InstrumentBundle,
) -> CommandResult:
    slope = (step.arg1 or "").strip().upper()
    bundle.scope.set_trigger_slope(slope)
    label = bundle.scope._SLOPE_LABELS.get(slope, slope)
    return CommandResult(message=f"Flanco de disparo: {label}")


def cmd_osc_timescale(
    _engine: TestExecutiveEngine,
    step: TestStep,
    bundle: InstrumentBundle,
) -> CommandResult:
    try:
        scale = float(step.arg1)
    except (ValueError, TypeError) as exc:
        raise EngineError(f"OSC_TIMESCALE: arg1 debe ser un numero (s/div): {exc}") from exc
    bundle.scope.set_timescale(scale)
    return CommandResult(message=f"Base de tiempo: {scale:.3E} s/div")


def cmd_end(
    _engine: TestExecutiveEngine,
    _step: TestStep,
    _bundle: InstrumentBundle,
) -> CommandResult:
    return CommandResult(stop_program=True, message="Fin de programa.")


COMMAND_DISPATCH = {
    "RESET": cmd_reset,
    "LOAD": cmd_load,
    "SUM": cmd_sum,
    "COMP": cmd_comp,
    "IF": cmd_if,
    "JMP": cmd_jmp,
    "TXT": cmd_txt,
    "WAIT": cmd_wait,
    "OSC_AUTOSCALE": cmd_osc_autoscale,
    "OSC_MEASURE": cmd_osc_measure,
    "OSC_TIMESCALE": cmd_osc_timescale,
    "OSC_SLOPE": cmd_osc_slope,
    "LOG": cmd_log,
    "END": cmd_end,
}
