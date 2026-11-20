from ate.instrumento import ErrorDeInstrumento, InstrumentoSCPI

# Forma de onda en el CSV -> nombre SCPI de la serie DG1000Z (comandos :SOURce<n>:APPLy y :FUNCtion).
FORMAS = {"SIN": "SINusoid", "SQU": "SQUare", "RAMP": "RAMP", "PULSE": "PULSe", "NOISE": "NOISe", "DC": "DC"}
# Parámetro que se puede leer con GEN_READ -> consulta SCPI (la respuesta viene en notación científica).
LECTURAS = {
    "FREQ": "FREQuency?",
    "AMPL": "VOLTage?",
    "OFFSET": "VOLTage:OFFSet?",
    "DUTY": "FUNCtion:SQUare:DCYCle?",
}
ESTADOS = {"ON", "OFF"}

# Vendor ID de RIGOL y Product ID de la serie DG1000Z en el nombre de recurso USB.
ID_USB_DG1000Z = "0X1AB1::0X0642"


class Generador(InstrumentoSCPI):
    """Driver mínimo del generador RIGOL DG1022Z por VISA (DG1000Z Programming Guide).

    Ojo: el DG1022 (sin Z) es otra serie, con otra sintaxis (APPLy:SQUare:CH2, VOLTage:CH2...).
    Si se le pide un valor fuera de rango, el DG1000Z no da error: lo recorta al límite. Por eso
    existe GEN_READ, que lee lo que el equipo realmente quedó configurado.
    """

    nombre = "Generador"

    def __init__(self, visa, recurso: str, timeout_ms: int):
        super().__init__(visa, recurso or buscar_generador(visa), timeout_ms, modelo="DG1")

    # --- Configuración de la señal ---

    def aplicar(self, forma: str, frecuencia: float, amplitud: float, offset: float, canal: str = "CH1") -> None:
        """Forma, frecuencia, amplitud (Vpp) y offset en un solo comando, como indica el manual."""
        forma = _forma(forma)
        if forma == "DC":
            parametros = f"DEF,DEF,{offset:.4E}"
        elif forma == "NOISe":
            parametros = f"{amplitud:.4E},{offset:.4E}"
        else:
            parametros = f"{frecuencia:.6E},{amplitud:.4E},{offset:.4E}"
        self.enviar(f":SOURce{_canal(canal)}:APPLy:{forma} {parametros}")

    def funcion(self, canal: str, forma: str) -> None:
        self.enviar(f":SOURce{_canal(canal)}:FUNCtion {_forma(forma)}")

    def frecuencia(self, canal: str, hertz: float) -> None:
        self.enviar(f":SOURce{_canal(canal)}:FREQuency {hertz:.6E}")

    def amplitud(self, canal: str, volts_pp: float) -> None:
        self.enviar(f":SOURce{_canal(canal)}:VOLTage {volts_pp:.4E}")

    def offset(self, canal: str, volts: float) -> None:
        self.enviar(f":SOURce{_canal(canal)}:VOLTage:OFFSet {volts:.4E}")

    def ciclo_de_trabajo(self, canal: str, porcentaje: float) -> None:
        self.enviar(f":SOURce{_canal(canal)}:FUNCtion:SQUare:DCYCle {porcentaje:.4E}")

    # --- Salida ---

    def carga(self, canal: str, valor) -> None:
        """Impedancia de carga que supone el generador: INF (alta impedancia) o de 1 a 10000 ohm.

        El generador escala la amplitud y el offset según este valor; con la entrada de 1 Mohm del
        osciloscopio corresponde INF, si no la tensión medida es el doble de la programada.
        """
        if str(valor).upper() in ("INF", "HIGHZ"):
            self.enviar(f":OUTPut{_canal(canal)}:IMPedance INFinity")
            return
        ohm = int(float(valor))
        if not 1 <= ohm <= 10000:
            raise ErrorDeInstrumento(f"Carga inválida: {valor!r}. Use INF o un valor de 1 a 10000 ohm.")
        self.enviar(f":OUTPut{_canal(canal)}:IMPedance {ohm}")

    def salida(self, canal: str, estado: str) -> None:
        estado = estado.upper()
        if estado not in ESTADOS:
            raise ErrorDeInstrumento(f"Estado de salida inválido: {estado!r}. Use ON u OFF.")
        self.enviar(f":OUTPut{_canal(canal)} {estado}")

    def apagar_salidas(self) -> None:
        for canal in ("CH1", "CH2"):
            self.salida(canal, "OFF")

    # --- Lectura de la configuración ---

    def leer(self, canal: str, parametro: str) -> float:
        parametro = parametro.upper()
        if parametro not in LECTURAS:
            raise ErrorDeInstrumento(f"Parámetro no soportado: {parametro!r}. Use FREQ, AMPL, OFFSET o DUTY.")
        return float(self.consultar(f":SOURce{_canal(canal)}:{LECTURAS[parametro]}"))


def buscar_generador(visa) -> str:
    """Primer DG1000Z conectado por USB, para no depender del número de serie en config.py."""
    for recurso in visa.list_resources():
        if ID_USB_DG1000Z in recurso.upper():
            return recurso
    raise ErrorDeInstrumento("No se encontró ningún generador RIGOL DG1000Z conectado por USB.")


def _canal(canal: str) -> int:
    # En el CSV se escribe CH1 o CH2 (vacío = canal 1); el DG1022Z tiene dos canales.
    numero = int("".join(c for c in canal if c.isdigit()) or "1")
    if numero not in (1, 2):
        raise ErrorDeInstrumento(f"Canal inválido: {canal!r}. Use CH1 o CH2.")
    return numero


def _forma(forma: str) -> str:
    forma = forma.upper()
    if forma not in FORMAS:
        raise ErrorDeInstrumento(f"Forma de onda inválida: {forma!r}. Use {', '.join(FORMAS)}.")
    return FORMAS[forma]
