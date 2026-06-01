from __future__ import annotations

import time
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

    def set_timescale(self, seconds_per_div: float) -> None:
        self._visa.write(f":TIMebase:MAIN:SCALe {seconds_per_div:.3E}")
        self._visa.wait_opc()

    _SLOPES = {"POS": "POSitive", "NEG": "NEGative", "RFAL": "RFALl"}
    _SLOPE_LABELS = {"POS": "ascendente (POS)", "NEG": "descendente (NEG)", "RFAL": "ambos (RFAL)"}

    def set_trigger_slope(self, slope: str) -> None:
        slope = slope.strip().upper()
        if slope not in self._SLOPES:
            raise InstrumentError(f"Flanco no valido: {slope!r}. Use POS, NEG o RFAL.")
        self._visa.write(f":TRIGger:EDGe:SLOPe {self._SLOPES[slope]}")
        self._visa.wait_opc()

    _MEASURE_ERROR = "measure error!"

    def measure(self, measurement: str, channel: str = "CHAN1") -> float:
        measurement = measurement.strip().upper()
        if measurement not in self._MEASUREMENTS:
            raise InstrumentError(f"Medicion no soportada para RIGOL: {measurement}")
        source = self._normalize_channel(channel)
        cmd = f":MEASure:ITEM? {self._MEASUREMENTS[measurement]},{source}"

        response = ""
        for attempt in range(3):
            response = self._visa.query(cmd)
            if self._MEASURE_ERROR not in response.lower():
                break
            if attempt < 2:
                time.sleep(0.5)
        else:
            raise InstrumentError(
                f"El osciloscopio no pudo medir {measurement} en {channel} "
                f"tras 3 intentos: el instrumento reporto '{response}'."
            )

        try:
            return float(response)
        except ValueError as exc:
            raise InstrumentError(
                f"El osciloscopio devolvio un valor inesperado para {measurement} "
                f"en {channel}: {response!r}"
            ) from exc

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
