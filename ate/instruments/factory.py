from __future__ import annotations

from dataclasses import dataclass

from ..config import RIGOL_SCOPE_RESOURCE, RIGOL_TIMEOUT_MS
from .rigol_scope import RigolDS1000ZEOscilloscope
from .visa import InstrumentError, VisaInstrument


@dataclass
class InstrumentBundle:
    scope: RigolDS1000ZEOscilloscope

    def close(self) -> None:
        self.scope.close()


def _build_scope() -> RigolDS1000ZEOscilloscope:
    visa = VisaInstrument(RIGOL_SCOPE_RESOURCE, timeout_ms=RIGOL_TIMEOUT_MS)
    try:
        identity = visa.query("*IDN?")
        # Verificar identidad previene operar sobre el instrumento equivocado si la dirección VISA apunta a otro equipo.
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
