from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_PROGRAMAS = RAIZ / "programas_tp"
CARPETA_REPORTES = RAIZ / "reportes"
LOGO = RAIZ / "ate" / "logo.png"

# Identificación de la estación que aparece en el reporte.
ESTACION = "ATE-UNI-01"

# VID 0x1AB1, PID 0x0517 y número de serie del osciloscopio. Si se cambia el equipo, se cambia esta línea.
RECURSO_OSCILOSCOPIO = "USB0::0x1AB1::0x0517::DS1ZE243207925::INSTR"

# VID 0x1AB1 y PID 0x0642 del generador DG1022Z (serie DG1000Z), conectado a otro puerto USB.
# Vacío: el TE usa el primer DG1000Z que encuentra; con más de uno, poner acá el recurso completo.
RECURSO_GENERADOR = ""

TIMEOUT_MS = 10000

# Tiempo durante el cual el osciloscopio acumula adquisiciones en OSC_MEASURE_STAT.
SEGUNDOS_ESTADISTICA = 3
