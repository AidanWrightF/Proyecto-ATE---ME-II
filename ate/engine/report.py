from __future__ import annotations

import time
from pathlib import Path

from ..config import REPORTS_DIR, STATION_ID
from .models import ProgramMetadata, RunResult

# Anchos de columna de la tabla de pasos del reporte.
_COLUMNS = (
    ("Linea", 6),
    ("Paso", 34),
    ("Medido", 12),
    ("Lim.Inf", 11),
    ("Lim.Sup", 11),
    ("Unidad", 7),
    ("Estado", 8),
    ("Dur[s]", 9),
)
_WIDTH = sum(width for _, width in _COLUMNS) + len(_COLUMNS) - 1


def _row(values: tuple[str, ...]) -> str:
    cells = [str(value)[:width].ljust(width) for value, (_, width) in zip(values, _COLUMNS)]
    return " ".join(cells)


def _build_report_text(metadata: ProgramMetadata, result: RunResult) -> str:
    duration_s = result.finished_at - result.started_at
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(result.started_at))

    lines: list[str] = []
    lines.append("=" * _WIDTH)
    lines.append("REPORTE DE PRUEBA - TEST EXECUTIVE".center(_WIDTH))
    lines.append("=" * _WIDTH)
    lines.append(f"TP        : {metadata.name} v{metadata.version}")
    lines.append(f"Archivo   : {Path(metadata.path).name if metadata.path else '-'}")
    lines.append(f"Estacion  : {STATION_ID}")
    lines.append(f"Fecha     : {when}")
    lines.append(f"Duracion  : {duration_s:.3f} s")
    lines.append(f"RESULTADO : {result.overall_status}")
    lines.append("-" * _WIDTH)
    lines.append(_row(tuple(name for name, _ in _COLUMNS)))
    lines.append("-" * _WIDTH)
    for step in result.steps:
        lines.append(
            _row(
                (
                    step.line,
                    step.name,
                    step.measured,
                    step.low,
                    step.high,
                    step.unit,
                    step.status,
                    step.duration,
                )
            )
        )
    lines.append("-" * _WIDTH)

    if result.registers:
        lines.append("Registros finales:")
        for name, value in result.registers.items():
            lines.append(f"  {name} = {value}")
        lines.append("-" * _WIDTH)

    lines.append("=" * _WIDTH)
    return "\n".join(lines) + "\n"


def write_report(
    metadata: ProgramMetadata,
    result: RunResult,
    reports_dir: Path = REPORTS_DIR,
) -> Path:
    """Genera el reporte de texto de la ejecucion y devuelve la ruta del archivo."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(metadata.path).stem if metadata.path else "tp"
    filename = f"reporte_{stem}_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    path = reports_dir / filename
    path.write_text(_build_report_text(metadata, result), encoding="utf-8")
    return path
