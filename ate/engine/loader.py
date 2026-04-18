from __future__ import annotations

import csv
import io
from pathlib import Path

from .models import EngineError, ProgramMetadata, TestStep


def load_test_program(path: str | Path) -> tuple[ProgramMetadata, list[TestStep]]:
    path = Path(path)
    metadata: dict[str, str] = {}
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
