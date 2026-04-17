from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import pyvisa  # type: ignore
except ImportError:  # pragma: no cover
    pyvisa = None


RIGOL_SCOPE_RESOURCE = "USB0::0x1AB1::0x0517::DS1ZE243207925::INSTR"
RIGOL_TIMEOUT_MS = 5000


class InstrumentError(RuntimeError):
    pass


class VisaInstrument:
    def __init__(self, resource_name: str, timeout_ms: int = RIGOL_TIMEOUT_MS) -> None:
        if pyvisa is None:
            raise InstrumentError("PyVISA no esta instalado.")
        self._resource_manager = pyvisa.ResourceManager()
        self._instrument = self._resource_manager.open_resource(resource_name)
        self._instrument.timeout = timeout_ms
        self._instrument.write_termination = "\n"
        self._instrument.read_termination = "\n"
        self.resource_name = resource_name

    def write(self, command: str) -> None:
        self._instrument.write(command)

    def query(self, command: str) -> str:
        return str(self._instrument.query(command)).strip()

    def wait_opc(self) -> None:
        self.query("*OPC?")

    def close(self) -> None:
        try:
            self._instrument.close()
        finally:
            self._resource_manager.close()


class RigolDS1000ZEOscilloscope:
    _MEASUREMENTS = {
        "VPP": "VPP",
        "FREQ": "FREQuency",
        "RISE": "RTIMe",
        "FALL": "FTIMe",
        "PWIDTH": "PWIDth",
        "PERIOD": "PERiod",
        "VMAX": "VMAX",
        "VMIN": "VMIN",
    }

    def __init__(self, visa: VisaInstrument, identity: Optional[str] = None) -> None:
        self._visa = visa
        self._identity = identity

    def identify(self) -> str:
        return self._identity or self._visa.query("*IDN?")

    def reset(self) -> None:
        self._visa.write("*RST")
        self._visa.wait_opc()

    def autoscale(self) -> None:
        self._visa.write(":AUToscale")
        self._visa.wait_opc()

    def measure(self, measurement: str, channel: str = "CHAN1") -> float:
        measurement = measurement.strip().upper()
        if measurement not in self._MEASUREMENTS:
            raise InstrumentError(f"Medicion no soportada para RIGOL: {measurement}")
        source = self._normalize_channel(channel)
        response = self._visa.query(
            f":MEASure:ITEM? {self._MEASUREMENTS[measurement]},{source}"
        )
        return float(response)

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        channel = channel.strip().upper()
        if channel.startswith("CHAN"):
            suffix = "".join(ch for ch in channel if ch.isdigit())
            if suffix:
                return f"CHANnel{suffix}"
        return channel

    def system_error(self) -> str:
        return self._visa.query(":SYSTem:ERRor?")

    def close(self) -> None:
        self._visa.close()


@dataclass
class InstrumentBundle:
    scope: object

    def close(self) -> None:
        self.scope.close()


def _build_scope():
    visa = VisaInstrument(RIGOL_SCOPE_RESOURCE, timeout_ms=RIGOL_TIMEOUT_MS)
    try:
        identity = visa.query("*IDN?")
        if "RIGOL" not in identity.upper():
            raise InstrumentError(
                f"El recurso configurado no corresponde a un osciloscopio RIGOL. '*IDN?' devolvio: {identity}"
            )
        return RigolDS1000ZEOscilloscope(visa, identity=identity)
    except Exception:
        visa.close()
        raise


def open_instruments() -> InstrumentBundle:
    return InstrumentBundle(scope=_build_scope())
