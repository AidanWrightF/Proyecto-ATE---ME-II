import time
from pathlib import Path

from ate import config
from ate.motor import Resultado
from ate.programa import Programa

# Columnas de la tabla de pasos; el ".34" recorta los nombres largos.
FILA = "{:<6} {:<34.34} {:<12} {:<11} {:<11} {:<7} {:<8} {:<9}"


def guardar_reporte(programa: Programa, resultado: Resultado) -> Path:
    """Escribe el reporte de la ejecución en reportes/ y devuelve su ruta."""
    config.CARPETA_REPORTES.mkdir(exist_ok=True)
    fecha = time.strftime("%Y%m%d-%H%M%S", time.localtime(resultado.inicio))
    ruta = config.CARPETA_REPORTES / f"reporte_{programa.archivo.stem}_{fecha}.txt"
    ruta.write_text(_texto_del_reporte(programa, resultado), encoding="utf-8")
    return ruta


def _texto_del_reporte(programa: Programa, resultado: Resultado) -> str:
    encabezado = FILA.format("Línea", "Paso", "Medido", "Lím.Inf", "Lím.Sup", "Unidad", "Estado", "Dur[s]")
    ancho = len(encabezado)
    doble = "=" * ancho
    simple = "-" * ancho
    fecha = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(resultado.inicio))

    lineas = [
        doble,
        "REPORTE DE PRUEBA - TEST EXECUTIVE".center(ancho),
        doble,
        f"TP        : {programa.nombre} v{programa.version}",
        f"Archivo   : {programa.archivo.name}",
        f"Estación  : {config.ESTACION}",
        f"Fecha     : {fecha}",
        f"Duración  : {resultado.duracion:.3f} s",
        f"RESULTADO : {resultado.estado}",
        simple,
        encabezado,
        simple,
    ]
    for ejecutado in resultado.pasos:
        paso = ejecutado.paso
        lineas.append(FILA.format(
            paso.linea,
            paso.nombre,
            _numero(ejecutado.medido),
            _numero(ejecutado.minimo),
            _numero(ejecutado.maximo),
            paso.unidad,
            ejecutado.estado,
            f"{ejecutado.duracion:.3f}",
        ))
    lineas.append(simple)

    if resultado.registros:
        lineas.append("Registros finales:")
        lineas += [f"  {nombre} = {_numero(valor)}" for nombre, valor in resultado.registros.items()]
        lineas.append(simple)

    if resultado.capturas:
        lineas.append("Capturas de pantalla:")
        lineas += [f"  {ruta.name}" for ruta in resultado.capturas]
        lineas.append(simple)

    lineas.append(doble)
    return "\n".join(lineas) + "\n"


def _numero(valor) -> str:
    """Números con 6 cifras significativas; vacío si no hay valor; el texto se deja como está."""
    if valor is None:
        return ""
    return f"{valor:.6g}" if isinstance(valor, float) else str(valor)
