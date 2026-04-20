from __future__ import annotations

from pathlib import Path

# Raíz del proyecto (Code_TE/). Referencia central para localizar recursos.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# VID 0x1AB1, PID 0x0517 y número de serie identifican al osciloscopio físico; si se reemplaza el equipo, solo se actualiza esta línea.
RIGOL_SCOPE_RESOURCE = "USB0::0x1AB1::0x0517::DS1ZE243207925::INSTR"
RIGOL_TIMEOUT_MS = 5000
