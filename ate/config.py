from __future__ import annotations

from pathlib import Path

# Raíz del proyecto (Code_TE/). Referencia central para localizar recursos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directorios de recursos. Centralizados aquí para que ninguna capa los hardcodee.
PROGRAMS_DIR = PROJECT_ROOT / "programs_tp" / "examples"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Identificacion de la estacion para el reporte (no se pide al operario).
STATION_ID = "ATE-UNI-01"

# VID 0x1AB1, PID 0x0517 y número de serie identifican al osciloscopio físico; si se reemplaza el equipo, solo se actualiza esta línea.
RIGOL_SCOPE_RESOURCE = "USB0::0x1AB1::0x0517::DS1ZE243207986::INSTR"
RIGOL_TIMEOUT_MS = 10000
