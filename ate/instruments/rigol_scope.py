from __future__ import annotations

from typing import Optional

from .visa import InstrumentError, VisaInstrument


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
        # El protocolo SCPI del RIGOL exige la forma larga "CHANnelN"; "CHAN1" es solo para legibilidad en el CSV.
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
