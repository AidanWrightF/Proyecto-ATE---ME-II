from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Optional

try:
    import pyvisa  # type: ignore
except ImportError:  # pragma: no cover
    pyvisa = None


class InstrumentError(RuntimeError):
    pass


SCOPE_MODEL_AUTO = "AUTO"
SCOPE_MODEL_AGILENT = "AGILENT"
SCOPE_MODEL_RIGOL_DS1000Z_E = "RIGOL_DS1000Z_E"
SUPPORTED_SCOPE_MODELS = (
    SCOPE_MODEL_AUTO,
    SCOPE_MODEL_RIGOL_DS1000Z_E,
    SCOPE_MODEL_AGILENT,
)


@dataclass
class InstrumentConfig:
    mock_mode: bool = True
    scope_resource: str = ""
    generator_resource: str = ""
    timeout_ms: int = 5000
    scope_model: str = SCOPE_MODEL_AUTO


@dataclass
class MockSignalState:
    waveform: str = "SQU"
    frequency_hz: float = 1000.0
    amplitude_vpp: float = 2.0
    offset_v: float = 0.0
    duty_cycle: float = 50.0
    output_enabled: bool = False


class VisaInstrument:
    def __init__(self, resource_name: str, timeout_ms: int = 5000) -> None:
        if pyvisa is None:
            raise InstrumentError(
                "PyVISA no esta instalado. Use mock_mode=True o instale pyvisa."
            )
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


def list_visa_resources() -> tuple[str, ...]:
    if pyvisa is None:
        raise InstrumentError(
            "PyVISA no esta instalado. Use mock_mode=True o instale pyvisa."
        )
    resource_manager = pyvisa.ResourceManager()
    try:
        return tuple(str(resource) for resource in resource_manager.list_resources())
    finally:
        resource_manager.close()


class MockDDSFunctionGenerator:
    def __init__(self, state: MockSignalState) -> None:
        self._state = state

    def identify(self) -> str:
        return "MOCK,DDS Function Generator,MODEL-FAKE,1.0"

    def reset(self) -> None:
        self._state.waveform = "SQU"
        self._state.frequency_hz = 1000.0
        self._state.amplitude_vpp = 2.0
        self._state.offset_v = 0.0
        self._state.duty_cycle = 50.0
        self._state.output_enabled = False

    def set_square(
        self,
        frequency_hz: float,
        amplitude_vpp: float,
        offset_v: float = 0.0,
        duty_cycle: float = 50.0,
    ) -> None:
        self._state.waveform = "SQU"
        self._state.frequency_hz = float(frequency_hz)
        self._state.amplitude_vpp = float(amplitude_vpp)
        self._state.offset_v = float(offset_v)
        self._state.duty_cycle = float(duty_cycle)

    def output(self, enabled: bool) -> None:
        self._state.output_enabled = bool(enabled)

    def system_error(self) -> str:
        return "0,No error"

    def close(self) -> None:
        return None


class NullFunctionGenerator:
    def identify(self) -> str:
        return "NO_GENERATOR,Not configured,N/A,1.0"

    def reset(self) -> None:
        return None

    def set_square(
        self,
        frequency_hz: float,
        amplitude_vpp: float,
        offset_v: float = 0.0,
        duty_cycle: float = 50.0,
    ) -> None:
        del frequency_hz, amplitude_vpp, offset_v, duty_cycle
        raise InstrumentError(
            "Este TP requiere un generador, pero generator_resource no esta configurado."
        )

    def output(self, enabled: bool) -> None:
        del enabled
        return None

    def system_error(self) -> str:
        return "0,No generator configured"

    def close(self) -> None:
        return None


class MockAgilentOscilloscope:
    def __init__(self, state: MockSignalState) -> None:
        self._state = state

    def identify(self) -> str:
        return "MOCK,Agilent Oscilloscope,DSO-FAKE,1.0"

    def reset(self) -> None:
        return None

    def autoscale(self) -> None:
        time.sleep(0.1)

    def measure(self, measurement: str, channel: str = "CHAN1") -> float:
        del channel
        if not self._state.output_enabled:
            return 0.0

        measurement = measurement.strip().upper()
        period = 1.0 / self._state.frequency_hz if self._state.frequency_hz else 0.0
        rise_time = max(250e-9, period * 0.0012)
        fall_time = max(250e-9, period * 0.0011)
        pulse_width = period * (self._state.duty_cycle / 100.0)

        values = {
            "VPP": self._state.amplitude_vpp,
            "FREQ": self._state.frequency_hz,
            "RISE": rise_time,
            "FALL": fall_time,
            "PWIDTH": pulse_width,
            "PERIOD": period,
            "VMAX": self._state.offset_v + (self._state.amplitude_vpp / 2.0),
            "VMIN": self._state.offset_v - (self._state.amplitude_vpp / 2.0),
        }
        if measurement not in values:
            raise InstrumentError(f"Medicion no soportada en mock: {measurement}")

        nominal = values[measurement]
        noise = 1.0 + random.uniform(-0.01, 0.01)
        return nominal * noise

    def close(self) -> None:
        return None


class DDSFunctionGenerator:
    def __init__(self, visa: VisaInstrument) -> None:
        self._visa = visa

    def identify(self) -> str:
        return self._visa.query("*IDN?")

    def reset(self) -> None:
        self._visa.write("*RST")
        self._visa.wait_opc()

    def set_square(
        self,
        frequency_hz: float,
        amplitude_vpp: float,
        offset_v: float = 0.0,
        duty_cycle: float = 50.0,
    ) -> None:
        self._visa.write("FUNC SQU")
        self._visa.write(f"FREQ {frequency_hz}")
        self._visa.write(f"VOLT {amplitude_vpp}")
        self._visa.write(f"VOLT:OFFS {offset_v}")
        self._visa.write(f"FUNC:SQU:DCYC {duty_cycle}")
        self._visa.wait_opc()

    def output(self, enabled: bool) -> None:
        self._visa.write(f"OUTP {'ON' if enabled else 'OFF'}")
        self._visa.wait_opc()

    def system_error(self) -> str:
        return self._visa.query("SYST:ERR?")

    def close(self) -> None:
        self._visa.close()


class AgilentOscilloscope:
    _MEASUREMENTS = {
        "VPP": "VPP",
        "FREQ": "FREQuency",
        "RISE": "RISetime",
        "FALL": "FALLtime",
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
            raise InstrumentError(f"Medicion no soportada: {measurement}")
        self._visa.write(f":MEASure:SOURce {self._normalize_channel(channel)}")
        response = self._visa.query(f":MEASure:{self._MEASUREMENTS[measurement]}?")
        return float(response)

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        channel = channel.strip().upper()
        if channel.startswith("CHAN"):
            suffix = "".join(ch for ch in channel if ch.isdigit())
            if suffix:
                return f"CHANnel{suffix}"
        return channel

    def close(self) -> None:
        self._visa.close()


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
    generator: object
    mock_mode: bool

    def close(self) -> None:
        try:
            self.scope.close()
        finally:
            self.generator.close()


def _require_real_resource(resource_name: str, label: str) -> str:
    resource_name = resource_name.strip()
    if not resource_name:
        raise InstrumentError(
            f"Modo real requiere configurar {label}. Use un recurso VISA USB/ASRL, por ejemplo "
            f"'USB0::...::INSTR' o 'ASRL4::INSTR'."
        )
    return resource_name


def _resolve_scope_model(scope_model: str, identity: str) -> str:
    normalized_model = (scope_model or SCOPE_MODEL_AUTO).strip().upper()
    if normalized_model not in SUPPORTED_SCOPE_MODELS:
        raise InstrumentError(
            f"Modelo de osciloscopio no soportado: {scope_model}. "
            f"Opciones validas: {', '.join(SUPPORTED_SCOPE_MODELS)}"
        )

    identity_upper = identity.upper()
    if normalized_model == SCOPE_MODEL_AUTO:
        if "RIGOL" in identity_upper and "DS" in identity_upper:
            return SCOPE_MODEL_RIGOL_DS1000Z_E
        if any(
            vendor in identity_upper
            for vendor in ("AGILENT", "KEYSIGHT", "HEWLETT-PACKARD")
        ):
            return SCOPE_MODEL_AGILENT
        raise InstrumentError(
            f"No se pudo autodetectar el osciloscopio a partir de '*IDN?': {identity}"
        )

    if normalized_model == SCOPE_MODEL_RIGOL_DS1000Z_E and "RIGOL" not in identity_upper:
        raise InstrumentError(
            f"El recurso configurado no parece ser un RIGOL DS1000Z-E. '*IDN?' devolvio: {identity}"
        )
    if normalized_model == SCOPE_MODEL_AGILENT and not any(
        vendor in identity_upper for vendor in ("AGILENT", "KEYSIGHT", "HEWLETT-PACKARD")
    ):
        raise InstrumentError(
            f"El recurso configurado no parece ser un osciloscopio Agilent/Keysight. "
            f"'*IDN?' devolvio: {identity}"
        )
    return normalized_model


def _build_scope(config: InstrumentConfig):
    scope_resource = _require_real_resource(config.scope_resource, "scope_resource")
    visa = VisaInstrument(scope_resource, timeout_ms=config.timeout_ms)
    try:
        identity = visa.query("*IDN?")
        scope_model = _resolve_scope_model(config.scope_model, identity)
        if scope_model == SCOPE_MODEL_RIGOL_DS1000Z_E:
            return RigolDS1000ZEOscilloscope(visa, identity=identity)
        return AgilentOscilloscope(visa, identity=identity)
    except Exception:
        visa.close()
        raise


def open_instruments(config: Optional[InstrumentConfig] = None) -> InstrumentBundle:
    config = config or InstrumentConfig()
    if config.mock_mode:
        state = MockSignalState()
        return InstrumentBundle(
            scope=MockAgilentOscilloscope(state),
            generator=MockDDSFunctionGenerator(state),
            mock_mode=True,
        )

    generator_resource = config.generator_resource.strip()
    if generator_resource:
        generator = DDSFunctionGenerator(
            VisaInstrument(generator_resource, timeout_ms=config.timeout_ms)
        )
    else:
        generator = NullFunctionGenerator()
    try:
        scope = _build_scope(config)
    except Exception:
        generator.close()
        raise
    return InstrumentBundle(scope=scope, generator=generator, mock_mode=False)
