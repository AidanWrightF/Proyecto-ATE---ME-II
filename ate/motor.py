import logging
import time
from dataclasses import dataclass
from pathlib import Path

import pyvisa

from ate import config
from ate.comandos import COMANDOS, ErrorDePrueba, OperarioCancelo
from ate.generador import Generador
from ate.osciloscopio import Osciloscopio
from ate.programa import Paso, Programa


@dataclass
class PasoEjecutado:
    paso: Paso
    estado: str = "PASS"
    medido: float | None = None
    minimo: float | None = None  # límites ya resueltos (pueden venir de un registro)
    maximo: float | None = None
    duracion: float = 0.0


@dataclass
class Resultado:
    estado: str  # PASS, FAIL o ABORTADO
    inicio: float
    duracion: float
    pasos: list[PasoEjecutado]
    registros: dict
    capturas: list[Path]


class Motor:
    """Ejecuta un Test Program paso a paso.

    al_avanzar(actual, total) informa el progreso y preguntar(mensaje) -> bool
    le pide una confirmación al operario. Ambas las provee la interfaz.
    """

    def __init__(self, al_avanzar, preguntar):
        self.al_avanzar = al_avanzar
        self.preguntar = preguntar
        # Estado que leen y modifican los comandos durante la ejecución.
        self.programa = None
        self.registros = {}
        self.capturas = []  # imágenes guardadas por OSC_SCREENSHOT
        self.osc = None
        self.gen = None  # sólo se conecta si el TP usa instrucciones GEN_
        self._visa = None
        self.siguiente = 0  # índice del próximo paso; IF y JMP lo cambian
        self.terminado = False  # END lo pone en True

    def ejecutar(self, programa: Programa) -> Resultado:
        self.programa = programa
        self.registros = {}
        self.capturas = []
        self.terminado = False
        self._indice_de_linea = {paso.linea: i for i, paso in enumerate(programa.pasos)}
        ejecutados = []
        total = len(programa.pasos)
        inicio = time.time()
        logging.info("Inicio de prueba: %s v%s", programa.nombre, programa.version)
        usa_generador = any(paso.comando.startswith("GEN_") for paso in programa.pasos)

        try:
            # Un único ResourceManager de VISA para los dos equipos, cada uno en su puerto USB.
            self._visa = pyvisa.ResourceManager()
            self.osc = Osciloscopio(self._visa, config.RECURSO_OSCILOSCOPIO, config.TIMEOUT_MS)
            if usa_generador:
                self.gen = Generador(self._visa, config.RECURSO_GENERADOR, config.TIMEOUT_MS)
            actual = 0
            while actual < total and not self.terminado:
                self.siguiente = actual + 1
                ejecutado = PasoEjecutado(programa.pasos[actual])
                ejecutados.append(ejecutado)
                self._ejecutar_paso(ejecutado)
                actual = self.siguiente
                self.al_avanzar(actual, total)
            estado = "PASS"
        except OperarioCancelo:
            estado = "ABORTADO"
            logging.error("El operario canceló la prueba.")
        except Exception as error:
            estado = "FAIL"
            logging.error("%s: %s", type(error).__name__, error)
        finally:
            self._cerrar_instrumentos()

        logging.info("Resultado: %s", estado)
        return Resultado(estado, inicio, time.time() - inicio, ejecutados, dict(self.registros), list(self.capturas))

    def _cerrar_instrumentos(self) -> None:
        # Pase lo que pase (PASS, FAIL o ABORTADO), el generador queda con las salidas apagadas.
        if self.gen is not None:
            try:
                self.gen.apagar_salidas()
            except Exception as error:
                logging.error("No se pudieron apagar las salidas del generador: %s", error)
            self.gen.cerrar()
            self.gen = None
        if self.osc is not None:
            self.osc.cerrar()
            self.osc = None
        if self._visa is not None:
            self._visa.close()
            self._visa = None

    def _ejecutar_paso(self, ejecutado: PasoEjecutado) -> None:
        paso = ejecutado.paso
        logging.info("Línea %s: %s (%s)", paso.linea, paso.nombre, paso.comando)
        inicio = time.perf_counter()
        try:
            comando = COMANDOS.get(paso.comando)
            if comando is None:
                raise ErrorDePrueba(f"Comando desconocido: {paso.comando}")
            ejecutado.medido = comando(self, paso)
            if ejecutado.medido is not None:
                self._verificar_limites(ejecutado)
        except Exception:
            ejecutado.estado = "FAIL"
            raise
        finally:
            ejecutado.duracion = time.perf_counter() - inicio

    def _verificar_limites(self, ejecutado: PasoEjecutado) -> None:
        paso, medido = ejecutado.paso, ejecutado.medido
        ejecutado.minimo = self.numero(paso.minimo) if paso.minimo else None
        ejecutado.maximo = self.numero(paso.maximo) if paso.maximo else None
        if ejecutado.minimo is not None and medido < ejecutado.minimo:
            raise ErrorDePrueba(f"{paso.nombre}: {medido:.6g} {paso.unidad} está por debajo de {ejecutado.minimo:.6g}")
        if ejecutado.maximo is not None and medido > ejecutado.maximo:
            raise ErrorDePrueba(f"{paso.nombre}: {medido:.6g} {paso.unidad} está por encima de {ejecutado.maximo:.6g}")

    def valor(self, texto: str):
        """Interpreta un argumento del TP: nombre de registro, número o texto."""
        if texto in self.registros:
            return self.registros[texto]
        try:
            return float(texto)
        except ValueError:
            return texto

    def numero(self, texto: str) -> float:
        return float(self.valor(texto))

    def saltar_a(self, linea: int) -> None:
        if linea not in self._indice_de_linea:
            raise ErrorDePrueba(f"No existe la línea {linea} para saltar.")
        self.siguiente = self._indice_de_linea[linea]
