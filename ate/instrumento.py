"""Lo común a los instrumentos SCPI del banco: conexión VISA, identificación, sincronización y cola de errores."""

import logging


class ErrorDeInstrumento(Exception):
    pass


class InstrumentoSCPI:
    """Base de los drivers del osciloscopio y del generador.

    Abre el recurso VISA y verifica con *IDN? que el equipo sea un RIGOL cuyo modelo empiece con
    `modelo` ("DS1" para el osciloscopio, "DG1" para el generador). Como los dos equipos son RIGOL,
    revisar sólo la marca no alcanza para detectar recursos cruzados en config.py.
    """

    nombre = "Instrumento"

    def __init__(self, visa, recurso: str, timeout_ms: int, modelo: str):
        self._equipo = visa.open_resource(recurso)
        self._equipo.timeout = timeout_ms
        self._equipo.write_termination = "\n"
        self._equipo.read_termination = "\n"

        identidad = self.consultar("*IDN?")
        campos = [campo.strip().upper() for campo in identidad.split(",")]
        if len(campos) < 2 or "RIGOL" not in campos[0] or not campos[1].startswith(modelo):
            self.cerrar()
            raise ErrorDeInstrumento(f"{self.nombre}: se esperaba un RIGOL {modelo}... y respondió {identidad!r}")
        logging.info("%s: %s", self.nombre, identidad)
        self.enviar("*CLS")  # vacía la cola de errores para que solo cuenten los de esta prueba

    def consultar(self, comando: str) -> str:
        return self._equipo.query(comando).strip()

    def enviar(self, comando: str) -> None:
        """Envía un comando y espera a que termine: *OPC? responde recién cuando el equipo terminó."""
        self._equipo.write(comando)
        self.consultar("*OPC?")

    def reset(self) -> None:
        self.enviar("*RST")

    def errores(self) -> list[str]:
        """Vacía la cola de errores del equipo. Cada error es un texto como '-224,"Illegal parameter value"'."""
        errores = []
        for _ in range(20):  # la cola del equipo es finita; el límite evita un lazo infinito si algo falla
            respuesta = self.consultar(":SYSTem:ERRor?")
            if int(respuesta.split(",")[0]) == 0:
                break
            errores.append(respuesta)
        return errores

    def cerrar(self) -> None:
        self._equipo.close()
