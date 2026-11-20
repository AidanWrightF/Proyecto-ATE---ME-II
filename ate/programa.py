import csv
from dataclasses import dataclass
from pathlib import Path

COLUMNAS = ["line", "name", "command", "arg1", "arg2", "arg3", "arg4", "low", "high", "unit"]


@dataclass
class Paso:
    """Una fila del Test Program."""

    linea: int
    nombre: str
    comando: str
    arg1: str
    arg2: str
    arg3: str
    arg4: str
    minimo: str
    maximo: str
    unidad: str


@dataclass
class Programa:
    nombre: str
    version: str
    archivo: Path
    pasos: list[Paso]


def cargar_programa(archivo: Path) -> Programa:
    """Lee un TP en CSV: primero los renglones '# CLAVE: valor' y después la tabla de pasos."""
    metadatos = {}
    filas = []
    for renglon in archivo.read_text(encoding="utf-8-sig").splitlines():
        renglon = renglon.strip()
        if renglon.startswith("#"):
            clave, _, valor = renglon[1:].partition(":")
            metadatos[clave.strip().upper()] = valor.strip()
        elif renglon:
            filas.append(renglon)

    lector = csv.DictReader(filas)
    if set(lector.fieldnames or []) != set(COLUMNAS):
        raise ValueError(f"El TP debe tener las columnas: {','.join(COLUMNAS)}")

    pasos = [_crear_paso(fila) for fila in lector if (fila["line"] or "").strip()]
    if not pasos:
        raise ValueError(f"El TP no tiene pasos: {archivo}")

    # Las filas pueden estar desordenadas: manda el número de línea.
    pasos.sort(key=lambda paso: paso.linea)
    lineas = [paso.linea for paso in pasos]
    if len(lineas) != len(set(lineas)):
        raise ValueError("El TP tiene números de línea repetidos.")

    return Programa(
        nombre=metadatos.get("TP_NAME", archivo.stem),
        version=metadatos.get("TP_VERSION", "1.0"),
        archivo=archivo,
        pasos=pasos,
    )


def _crear_paso(fila: dict) -> Paso:
    dato = {columna: (fila[columna] or "").strip() for columna in COLUMNAS}
    return Paso(
        linea=int(dato["line"]),
        nombre=dato["name"],
        comando=dato["command"].upper(),
        arg1=dato["arg1"],
        arg2=dato["arg2"],
        arg3=dato["arg3"],
        arg4=dato["arg4"],
        minimo=dato["low"],
        maximo=dato["high"],
        unidad=dato["unit"],
    )
