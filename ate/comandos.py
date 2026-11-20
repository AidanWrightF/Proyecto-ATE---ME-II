"""Una función por cada instrucción del TP.

Todas reciben el motor (registros, instrumentos, saltos) y el paso (fila del CSV).
Las que miden o calculan algo devuelven el valor, y el motor lo compara con los límites.
"""

import logging
import operator
import time

from ate import config


class ErrorDePrueba(Exception):
    """Un paso no se pudo ejecutar o su valor quedó fuera de los límites."""


class OperarioCancelo(Exception):
    """El operario presionó Cancelar en una instrucción manual (TXT)."""


COMPARADORES = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


# --- Registros y cálculos ---

def reiniciar(motor, paso):
    motor.registros.clear()
    motor.osc.reset()
    if motor.gen is not None:
        motor.gen.reset()  # el *RST del generador también apaga sus salidas


def cargar(motor, paso):
    _guardar(motor, paso.arg1, motor.valor(paso.arg2))


def sumar(motor, paso):
    return _calcular(motor, paso, operator.add)


def restar(motor, paso):
    return _calcular(motor, paso, operator.sub)


def multiplicar(motor, paso):
    return _calcular(motor, paso, operator.mul)


def dividir(motor, paso):
    if motor.numero(paso.arg2) == 0:
        raise ErrorDePrueba(f"División por cero: {paso.arg2} vale 0.")
    return _calcular(motor, paso, operator.truediv)


# --- Control del programa ---

def salto_condicional(motor, paso):
    comparar = COMPARADORES.get(paso.arg2)
    if comparar is None:
        raise ErrorDePrueba(f"Operador desconocido en IF: {paso.arg2!r}")
    if comparar(motor.valor(paso.arg1), motor.valor(paso.arg3)):
        motor.saltar_a(int(motor.numero(paso.arg4)))


def salto_incondicional(motor, paso):
    motor.saltar_a(int(motor.numero(paso.arg1)))


def pedir_confirmacion(motor, paso):
    mensaje = paso.arg1 or paso.nombre or "Confirme para continuar."
    if not motor.preguntar(mensaje):
        raise OperarioCancelo()


def esperar(motor, paso):
    time.sleep(motor.numero(paso.arg1 or "0"))


def mostrar_mensaje(motor, paso):
    logging.info(paso.arg1 or paso.nombre)


def fin(motor, paso):
    motor.terminado = True


# --- Osciloscopio: configuración ---

def autoescala(motor, paso):
    motor.osc.autoescala()


def sonda(motor, paso):
    motor.osc.sonda(paso.arg1, motor.numero(paso.arg2))


def acoplamiento(motor, paso):
    motor.osc.acoplamiento(paso.arg1, paso.arg2)


def limite_de_banda(motor, paso):
    motor.osc.limite_de_banda(paso.arg1, paso.arg2)


def escala_vertical(motor, paso):
    motor.osc.escala_vertical(paso.arg1, motor.numero(paso.arg2))


def offset_vertical(motor, paso):
    motor.osc.offset_vertical(paso.arg1, motor.numero(paso.arg2))


def base_de_tiempo(motor, paso):
    motor.osc.base_de_tiempo(motor.numero(paso.arg1))


def offset_horizontal(motor, paso):
    motor.osc.offset_horizontal(motor.numero(paso.arg1))


def fuente_de_disparo(motor, paso):
    motor.osc.fuente_de_disparo(paso.arg1)


def nivel_de_disparo(motor, paso):
    motor.osc.nivel_de_disparo(motor.numero(paso.arg1))


def flanco_de_disparo(motor, paso):
    motor.osc.flanco_de_disparo(paso.arg1)


def adquisicion(motor, paso):
    promedios = int(motor.numero(paso.arg2)) if paso.arg2 else None
    motor.osc.adquisicion(paso.arg1, promedios)


# --- Osciloscopio: control de la adquisición ---

def correr(motor, paso):
    motor.osc.correr()


def detener(motor, paso):
    motor.osc.detener()


def disparo_unico(motor, paso):
    motor.osc.disparo_unico()


# --- Osciloscopio: mediciones y diagnóstico ---

def medir(motor, paso):
    tipo = paso.arg1 or "VPP"
    canal = paso.arg2 or "CHAN1"
    valor = motor.osc.medir(tipo, canal)
    _guardar(motor, paso.arg3 or f"REG_{tipo}", valor)
    logging.info("%s en %s = %.6g %s", tipo, canal, valor, paso.unidad)
    return valor


def medir_estadistica(motor, paso):
    tipo = paso.arg1
    canal = paso.arg2 or "CHAN1"
    estadistico = paso.arg4 or "AVG"
    valor = motor.osc.estadistica(tipo, canal, estadistico, config.SEGUNDOS_ESTADISTICA)
    _guardar(motor, paso.arg3 or f"REG_{tipo}_{estadistico}", valor)
    logging.info("%s de %s en %s = %.6g %s", estadistico, tipo, canal, valor, paso.unidad)
    return valor


def verificar_errores(motor, paso):
    errores = motor.osc.errores()
    if errores:
        raise ErrorDePrueba(f"El osciloscopio rechazó comandos: {'; '.join(errores)}")


def captura_de_pantalla(motor, paso):
    config.CARPETA_REPORTES.mkdir(exist_ok=True)
    fecha = time.strftime("%Y%m%d-%H%M%S")
    ruta = config.CARPETA_REPORTES / f"captura_{motor.programa.archivo.stem}_{fecha}_linea{paso.linea}.png"
    ruta.write_bytes(motor.osc.captura_de_pantalla())
    motor.capturas.append(ruta)
    logging.info("Captura de pantalla guardada: %s", ruta.name)


# --- Generador: configuración de la señal y de la salida ---

def generador_aplicar(motor, paso):
    # GEN_APPLY trabaja sobre CH1, el canal que se usa en el banco; para CH2 están las instrucciones sueltas.
    offset = motor.numero(paso.arg4) if paso.arg4 else 0.0
    motor.gen.aplicar(paso.arg1, motor.numero(paso.arg2 or "0"), motor.numero(paso.arg3 or "0"), offset)


def generador_funcion(motor, paso):
    motor.gen.funcion(paso.arg1, paso.arg2)


def generador_frecuencia(motor, paso):
    motor.gen.frecuencia(paso.arg1, motor.numero(paso.arg2))


def generador_amplitud(motor, paso):
    motor.gen.amplitud(paso.arg1, motor.numero(paso.arg2))


def generador_offset(motor, paso):
    motor.gen.offset(paso.arg1, motor.numero(paso.arg2))


def generador_ciclo(motor, paso):
    motor.gen.ciclo_de_trabajo(paso.arg1, motor.numero(paso.arg2))


def generador_carga(motor, paso):
    motor.gen.carga(paso.arg1, motor.valor(paso.arg2 or "INF"))


def generador_salida(motor, paso):
    motor.gen.salida(paso.arg1, paso.arg2)


# --- Generador: lectura y diagnóstico ---

def generador_leer(motor, paso):
    parametro = (paso.arg2 or "FREQ").upper()
    valor = motor.gen.leer(paso.arg1, parametro)
    _guardar(motor, paso.arg3 or f"GEN_{parametro}", valor)
    logging.info("Generador %s: %s = %.6g %s", paso.arg1 or "CH1", parametro, valor, paso.unidad)
    return valor


def generador_errores(motor, paso):
    errores = motor.gen.errores()
    if errores:
        raise ErrorDePrueba(f"El generador rechazó comandos: {'; '.join(errores)}")


def _guardar(motor, registro, valor):
    if not registro:
        raise ErrorDePrueba("Falta el nombre del registro donde guardar el resultado.")
    motor.registros[registro] = valor


def _calcular(motor, paso, operacion):
    resultado = operacion(motor.numero(paso.arg1), motor.numero(paso.arg2))
    _guardar(motor, paso.arg3, resultado)
    return resultado


# Traduce el nombre del comando en el CSV a la función que lo ejecuta.
COMANDOS = {
    # Registros y cálculos
    "RESET": reiniciar,
    "LOAD": cargar,
    "SUM": sumar,
    "COMP": restar,
    "MUL": multiplicar,
    "DIV": dividir,
    # Control del programa
    "IF": salto_condicional,
    "JMP": salto_incondicional,
    "TXT": pedir_confirmacion,
    "WAIT": esperar,
    "LOG": mostrar_mensaje,
    "END": fin,
    # Osciloscopio: configuración
    "OSC_AUTOSCALE": autoescala,
    "OSC_PROBE": sonda,
    "OSC_COUPLING": acoplamiento,
    "OSC_BWLIMIT": limite_de_banda,
    "OSC_VSCALE": escala_vertical,
    "OSC_VOFFSET": offset_vertical,
    "OSC_TIMESCALE": base_de_tiempo,
    "OSC_TIMEOFFSET": offset_horizontal,
    "OSC_TRIG_SOURCE": fuente_de_disparo,
    "OSC_TRIG_LEVEL": nivel_de_disparo,
    "OSC_SLOPE": flanco_de_disparo,
    "OSC_ACQUIRE": adquisicion,
    # Osciloscopio: control de la adquisición
    "OSC_RUN": correr,
    "OSC_STOP": detener,
    "OSC_SINGLE": disparo_unico,
    # Osciloscopio: mediciones y diagnóstico
    "OSC_MEASURE": medir,
    "OSC_MEASURE_STAT": medir_estadistica,
    "OSC_CHECK_ERRORS": verificar_errores,
    "OSC_SCREENSHOT": captura_de_pantalla,
    # Generador: configuración de la señal y de la salida
    "GEN_APPLY": generador_aplicar,
    "GEN_FUNC": generador_funcion,
    "GEN_FREQ": generador_frecuencia,
    "GEN_AMPL": generador_amplitud,
    "GEN_OFFSET": generador_offset,
    "GEN_DUTY": generador_ciclo,
    "GEN_LOAD": generador_carga,
    "GEN_OUTPUT": generador_salida,
    # Generador: lectura y diagnóstico
    "GEN_READ": generador_leer,
    "GEN_CHECK_ERRORS": generador_errores,
}
