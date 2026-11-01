from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from ate import TestExecutiveEngine, write_report
from ate.config import PROGRAMS_DIR
from ate.engine.models import RunStatus

logger = logging.getLogger("ate")

_STYLE_NEUTRAL = "neutral.Horizontal.TProgressbar"
_STYLE_PASS = "pass.Horizontal.TProgressbar"
_STYLE_FAIL = "fail.Horizontal.TProgressbar"


class TEOperatorApp:
    """Interfaz minima del operario: elegir un TP y ver el avance en una barra.

    El operario no controla la ejecucion (no hay pausa/abort/reinicio: eso lo
    decide el propio TP) ni ve el detalle de pasos ni el log. Los resultados se
    entregan en un reporte de texto que se abre al finalizar.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Test Executive - RIGOL DS1202Z-E")
        self.root.geometry("560x150")
        self.root.minsize(480, 130)

        # Puente thread-safe entre el hilo del engine y el hilo de la GUI (tkinter no es thread-safe).
        self.event_queue: queue.Queue = queue.Queue()
        self.engine = TestExecutiveEngine(
            event_callback=self._enqueue_event,
            prompt_handler=self._prompt_operator,
        )
        self.run_thread: threading.Thread | None = None
        self._tp_paths: dict[str, Path] = {}

        self._build_ui()
        self._populate_programs()
        self.root.after(100, self._process_events)  # sondea la cola cada 100 ms desde el hilo de la UI

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure(_STYLE_NEUTRAL, background="#0d6efd")
        style.configure(_STYLE_PASS, background="#198754")
        style.configure(_STYLE_FAIL, background="#dc3545")

        top = ttk.Frame(self.root, padding=(16, 18, 16, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Test Program:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.tp_var = tk.StringVar()
        self.tp_combo = ttk.Combobox(top, textvariable=self.tp_var, state="readonly")
        self.tp_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.start_button = ttk.Button(top, text="START", width=12, command=self.start_test)
        self.start_button.grid(row=0, column=2)

        bar = ttk.Frame(self.root, padding=(16, 12, 16, 16))
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(
            bar, mode="determinate", style=_STYLE_NEUTRAL, maximum=100, value=0
        )
        self.progress.grid(row=0, column=0, sticky="ew", ipady=10)

    def _populate_programs(self) -> None:
        self._tp_paths = {}
        if PROGRAMS_DIR.exists():
            for csv_path in sorted(PROGRAMS_DIR.glob("*.csv")):
                self._tp_paths[csv_path.name] = csv_path
        names = list(self._tp_paths)
        self.tp_combo.configure(values=names)
        if names:
            self.tp_var.set(names[0])
        else:
            logger.error("No se encontraron TP (*.csv) en %s", PROGRAMS_DIR)

    def start_test(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            return

        path = self._tp_paths.get(self.tp_var.get())
        if path is None:
            logger.error("No hay ningun TP seleccionado para ejecutar.")
            return

        try:
            self.engine.load_program(path)
        except Exception as exc:  # TP invalido: el operario no debe ver el detalle, va a consola.
            logger.error("No se pudo cargar el TP %s: %s", path.name, exc)
            return

        self.progress.configure(style=_STYLE_NEUTRAL, maximum=max(len(self.engine.program), 1), value=0)
        self.start_button.configure(state="disabled")

        self.run_thread = threading.Thread(target=self._worker_run, daemon=True)
        self.run_thread.start()

    def _worker_run(self) -> None:
        try:
            result = self.engine.run()
            report_path = write_report(self.engine.metadata, result)
            self.event_queue.put(
                {
                    "type": "run_complete",
                    "overall_status": result.overall_status,
                    "report_path": str(report_path),
                }
            )
        except Exception:
            logger.exception("Fallo no controlado durante la ejecucion.")
        finally:
            self.event_queue.put({"type": "worker_finished"})

    def _enqueue_event(self, event: dict) -> None:
        self.event_queue.put(event)

    def _prompt_operator(self, message: str) -> bool:
        response_queue: queue.Queue = queue.Queue(maxsize=1)
        self.event_queue.put({"type": "prompt", "message": message, "response_queue": response_queue})
        return bool(response_queue.get())  # bloquea el hilo del engine hasta que la UI resuelva el diálogo

    def _process_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_events)

    def _handle_event(self, event: dict) -> None:
        event_type = event.get("type")

        if event_type == "progress":
            self.progress.configure(maximum=event.get("total") or self.progress["maximum"])
            self.progress["value"] = event.get("current", 0)
            return

        if event_type == "prompt":
            accepted = messagebox.askokcancel("Accion manual requerida", event.get("message", ""))
            event["response_queue"].put(accepted)
            return

        if event_type == "run_complete":
            status = event.get("overall_status", RunStatus.FAIL)
            self.progress["value"] = self.progress["maximum"]
            self.progress.configure(style=_STYLE_PASS if status == RunStatus.PASS else _STYLE_FAIL)
            report_path = event.get("report_path")
            if report_path:
                self._open_report(report_path)
            return

        if event_type == "worker_finished":
            self.start_button.configure(state="normal")
            return

    @staticmethod
    def _open_report(path: str) -> None:
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # Windows
        except AttributeError:
            webbrowser.open(Path(path).as_uri())  # fallback multiplataforma (Linux/Mac)
        except OSError as exc:
            logger.error("No se pudo abrir el reporte %s: %s", path, exc)
