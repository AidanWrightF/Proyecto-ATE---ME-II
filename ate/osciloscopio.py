import time

from ate.instrumento import ErrorDeInstrumento, InstrumentoSCPI

# Nombre de cada medición en el CSV -> nombre SCPI del RIGOL (serie DS1000Z, comando :MEASure:ITEM?).
# FREQ_CNT no está acá porque usa el contador de frecuencia, que tiene sus propios comandos.
MEDICIONES = {
    "VPP": "VPP",
    "VMAX": "VMAX",
    "VMIN": "VMIN",
    "VTOP": "VTOP",
    "VBASE": "VBASe",
    "VAMP": "VAMP",
    "VAVG": "VAVG",
    "VRMS": "VRMS",
    "OVERSHOOT": "OVERshoot",
    "PRESHOOT": "PREShoot",
    "FREQ": "FREQuency",
    "PERIOD": "PERiod",
    "PWIDTH": "PWIDth",
    "PDUTY": "PDUTy",
    "RISE": "RTIMe",
    "FALL": "FTIMe",
}
ESTADISTICOS = {"AVG": "AVERages", "DEV": "DEViation", "MIN": "MINimum", "MAX": "MAXimum", "CUR": "CURRent"}
FLANCOS = {"POS": "POSitive", "NEG": "NEGative", "RFAL": "RFALl"}
ACOPLAMIENTOS = {"DC", "AC", "GND"}
LIMITES_DE_BANDA = {"ON": "20M", "OFF": "OFF"}
TIPOS_DE_ADQUISICION = {"NORMAL": "NORMal", "AVERAGE": "AVERages", "PEAK": "PEAK", "HRES": "HRESolution"}

# El RIGOL devuelve este valor cuando la señal no se puede medir (fuera de pantalla o de rango).
SIN_MEDICION = 9.9e37


class Osciloscopio(InstrumentoSCPI):
    """Driver mínimo del RIGOL DS1202Z-E por VISA, usando comandos SCPI (DS1000Z Programming Guide)."""

    nombre = "Osciloscopio"

    def __init__(self, visa, recurso: str, timeout_ms: int):
        super().__init__(visa, recurso, timeout_ms, modelo="DS1")

    # --- Configuración ---

    def autoescala(self) -> None:
        self.enviar(":AUToscale")

    def sonda(self, canal: str, atenuacion: float) -> None:
        self.enviar(f":{_fuente(canal)}:PROBe {atenuacion:g}")

    def acoplamiento(self, canal: str, tipo: str) -> None:
        tipo = tipo.upper()
        if tipo not in ACOPLAMIENTOS:
            raise ErrorDeInstrumento(f"Acoplamiento inválido: {tipo!r}. Use DC, AC o GND.")
        self.enviar(f":{_fuente(canal)}:COUPling {tipo}")

    def limite_de_banda(self, canal: str, estado: str) -> None:
        estado = estado.upper()
        if estado not in LIMITES_DE_BANDA:
            raise ErrorDeInstrumento(f"Límite de banda inválido: {estado!r}. Use ON (20 MHz) u OFF.")
        self.enviar(f":{_fuente(canal)}:BWLimit {LIMITES_DE_BANDA[estado]}")

    def escala_vertical(self, canal: str, volts_por_division: float) -> None:
        self.enviar(f":{_fuente(canal)}:SCALe {volts_por_division:.3E}")

    def offset_vertical(self, canal: str, volts: float) -> None:
        self.enviar(f":{_fuente(canal)}:OFFSet {volts:.3E}")

    def base_de_tiempo(self, segundos_por_division: float) -> None:
        self.enviar(f":TIMebase:MAIN:SCALe {segundos_por_division:.3E}")

    def offset_horizontal(self, segundos: float) -> None:
        self.enviar(f":TIMebase:MAIN:OFFSet {segundos:.3E}")

    def fuente_de_disparo(self, canal: str) -> None:
        self.enviar(f":TRIGger:EDGe:SOURce {_fuente(canal)}")

    def nivel_de_disparo(self, volts: float) -> None:
        self.enviar(f":TRIGger:EDGe:LEVel {volts:.3E}")

    def flanco_de_disparo(self, flanco: str) -> None:
        flanco = flanco.upper()
        if flanco not in FLANCOS:
            raise ErrorDeInstrumento(f"Flanco inválido: {flanco!r}. Use POS, NEG o RFAL.")
        self.enviar(f":TRIGger:EDGe:SLOPe {FLANCOS[flanco]}")

    def adquisicion(self, tipo: str, promedios: int | None = None) -> None:
        tipo = tipo.upper()
        if tipo not in TIPOS_DE_ADQUISICION:
            raise ErrorDeInstrumento(f"Tipo de adquisición inválido: {tipo!r}. Use NORMAL, AVERAGE, PEAK o HRES.")
        self.enviar(f":ACQuire:TYPE {TIPOS_DE_ADQUISICION[tipo]}")
        if promedios:
            self.enviar(f":ACQuire:AVERages {promedios}")

    # --- Control de la adquisición ---

    def correr(self) -> None:
        self.enviar(":RUN")

    def detener(self) -> None:
        self.enviar(":STOP")

    def disparo_unico(self) -> None:
        self.enviar(":SINGle")

    # --- Mediciones ---

    def medir(self, tipo: str, canal: str) -> float:
        tipo = tipo.upper()
        if tipo == "FREQ_CNT":
            return self.frecuencia_con_contador(canal)
        if tipo not in MEDICIONES:
            raise ErrorDeInstrumento(f"Medición no soportada: {tipo}")

        consulta = f":MEASure:ITEM? {MEDICIONES[tipo]},{_fuente(canal)}"
        for _ in range(3):
            respuesta = self.consultar(consulta)
            if "measure error" not in respuesta.lower():
                break
            time.sleep(0.5)
        else:
            raise ErrorDeInstrumento(f"No se pudo medir {tipo} en {canal} tras 3 intentos: {respuesta}")

        valor = float(respuesta)
        if valor >= SIN_MEDICION:
            raise ErrorDeInstrumento(f"No hay señal medible para {tipo} en {canal}.")
        return valor

    def frecuencia_con_contador(self, canal: str) -> float:
        """Frecuencia del contador por hardware: más precisa que FREQ, que se calcula sobre la forma de onda en pantalla."""
        self.enviar(f":MEASure:COUNter:SOURce {_fuente(canal)}")
        for _ in range(5):
            time.sleep(0.5)  # el contador necesita un tiempo de compuerta antes de dar la primera lectura
            valor = float(self.consultar(":MEASure:COUNter:VALue?"))
            if 0 < valor < SIN_MEDICION:
                return valor
        raise ErrorDeInstrumento(f"El contador no pudo medir la frecuencia en {canal}.")

    def estadistica(self, tipo: str, canal: str, estadistico: str, segundos: float) -> float:
        """Promedio, desvío, mínimo o máximo de una medición acumulado durante `segundos` (con la adquisición en RUN)."""
        tipo, estadistico = tipo.upper(), estadistico.upper()
        if tipo not in MEDICIONES:
            raise ErrorDeInstrumento(f"Medición no soportada para estadística: {tipo}")
        if estadistico not in ESTADISTICOS:
            raise ErrorDeInstrumento(f"Estadístico inválido: {estadistico!r}. Use AVG, DEV, MIN, MAX o CUR.")

        item = f"{MEDICIONES[tipo]},{_fuente(canal)}"
        # El modo DIFFerence calcula el desvío estándar; el modo EXTRemum, el mínimo y el máximo.
        self.enviar(f":MEASure:STATistic:MODE {'DIFFerence' if estadistico == 'DEV' else 'EXTRemum'}")
        self.enviar(":MEASure:STATistic:DISPlay ON")
        self.enviar(f":MEASure:STATistic:ITEM {item}")
        self.enviar(":MEASure:STATistic:RESet")
        time.sleep(segundos)

        valor = float(self.consultar(f":MEASure:STATistic:ITEM? {ESTADISTICOS[estadistico]},{item}"))
        if valor >= SIN_MEDICION:
            raise ErrorDeInstrumento(f"No hay estadística disponible de {tipo} en {canal}.")
        return valor

    # --- Diagnóstico ---

    def captura_de_pantalla(self) -> bytes:
        """Imagen PNG de lo que muestra la pantalla (a color, sin invertir)."""
        return bytes(self._equipo.query_binary_values(":DISPlay:DATA? ON,OFF,PNG", datatype="B", container=bytearray))


def _fuente(canal: str) -> str:
    # El RIGOL espera la forma larga "CHANnel1"; en el CSV se escribe "CHAN1" por comodidad (vacío = canal 1).
    numero_de_canal = "".join(c for c in canal if c.isdigit()) or "1"
    return f"CHANnel{numero_de_canal}"
