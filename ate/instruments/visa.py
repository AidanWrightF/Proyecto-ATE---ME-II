from __future__ import annotations

try:
    import pyvisa  # type: ignore
except ImportError:  # pragma: no cover
    pyvisa = None


DEFAULT_VISA_TIMEOUT_MS = 5000


class InstrumentError(RuntimeError):
    pass


class VisaInstrument:
    def __init__(self, resource_name: str, timeout_ms: int = DEFAULT_VISA_TIMEOUT_MS) -> None:
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
