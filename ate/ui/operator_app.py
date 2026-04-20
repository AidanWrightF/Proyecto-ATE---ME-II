from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ate import ExecutionContext, TestExecutiveEngine
from ate.config import PROJECT_ROOT
from ate.engine.models import RunStatus, StepStatus

_PROGRAMS_DIR = PROJECT_ROOT / "programs_tp" / "examples"

_STATUS_COLORS: dict[str, str] = {
    RunStatus.TESTING: "#d97706",
    RunStatus.PASS: "#198754",
    RunStatus.FAIL: "#dc3545",
    RunStatus.ABORTED: "#dc3545",
}
_STATUS_LABELS: dict[str, str] = {
    RunStatus.TESTING: "TESTING...",
    RunStatus.PASS: "PASS",
    RunStatus.FAIL: "FAIL",
    RunStatus.ABORTED: "ABORTED",
}


class TEOperatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Test Executive - RIGOL DS1202Z-E")
        self.root.geometry("1280x840")
        self.root.minsize(1100, 740)

        # Puente thread-safe entre el hilo del engine y el hilo de la GUI (tkinter no es thread-safe).
        self.event_queue: queue.Queue = queue.Queue()
        self.engine = TestExecutiveEngine(
            event_callback=self._enqueue_event,
            prompt_handler=self._prompt_operator,
        )
        self.run_thread: threading.Thread | None = None
        self.loop_stop_event = threading.Event()
        self.current_program_path = _PROGRAMS_DIR / "tp_rigol_ch1_comp.csv"
        self.row_ids: dict[int, str] = {}
        self.paused = False

        self._build_ui()
        self._load_default_program()
        self.root.after(100, self._process_events)  # sondea la cola cada 100 ms desde el hilo de la UI

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=3)
        self.root.rowconfigure(4, weight=1)

        self._build_top_bar()
        self._build_status_panel()
        self._build_controls()
        self._build_table()
        self._build_log()

    def _build_top_bar(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 8))
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(5, weight=1)

        ttk.Label(frame, text="Estacion:").grid(row=0, column=0, sticky="w")
        self.station_var = tk.StringVar(value="ATE-UNI-01")
        ttk.Entry(frame, textvariable=self.station_var, width=18).grid(row=0, column=1, sticky="ew", padx=(4, 16))

        ttk.Label(frame, text="Operario:").grid(row=0, column=2, sticky="w")
        self.operator_var = tk.StringVar(value="Operario")
        ttk.Entry(frame, textvariable=self.operator_var, width=18).grid(row=0, column=3, sticky="ew", padx=(4, 16))

        ttk.Label(frame, text="N/S UUT:").grid(row=0, column=4, sticky="w")
        self.uut_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.uut_var, width=18).grid(row=0, column=5, sticky="ew", padx=(4, 16))

        ttk.Button(frame, text="Cargar TP...", command=self.load_program_dialog).grid(row=0, column=6, padx=4)

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Loop", variable=self.loop_var).grid(row=0, column=7, padx=(8, 0))

    def _build_status_panel(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Test Program", padding=(10, 6))
        frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(5, weight=1)

        self.tp_name_var = tk.StringVar(value="—")
        self.tp_version_var = tk.StringVar(value="—")
        self.tp_file_var = tk.StringVar(value="—")

        ttk.Label(frame, text="Nombre:").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.tp_name_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(4, 24))

        ttk.Label(frame, text="Version:").grid(row=0, column=2, sticky="w")
        ttk.Label(frame, textvariable=self.tp_version_var).grid(row=0, column=3, sticky="w", padx=(4, 24))

        ttk.Label(frame, text="Archivo:").grid(row=0, column=4, sticky="w")
        ttk.Label(frame, textvariable=self.tp_file_var, foreground="#0d6efd").grid(row=0, column=5, sticky="w", padx=4)

    def _build_controls(self) -> None:
        outer = ttk.Frame(self.root, padding=(10, 4))
        outer.grid(row=2, column=0, sticky="ew")
        outer.columnconfigure(3, weight=1)

        self.status_frame = tk.Frame(outer, bg="#6c757d", width=200, height=44)
        self.status_frame.grid(row=0, column=0, padx=(0, 16))
        self.status_frame.pack_propagate(False)
        self.status_text_var = tk.StringVar(value="READY")
        self.status_label = tk.Label(
            self.status_frame,
            textvariable=self.status_text_var,
            bg="#6c757d",
            fg="white",
            font=("Segoe UI", 14, "bold"),
        )
        self.status_label.pack(expand=True)

        ttk.Button(outer, text="START", width=12, command=self.start_test).grid(row=0, column=1, padx=4)
        self.pause_button = ttk.Button(outer, text="PAUSE", width=12, command=self.toggle_pause)
        self.pause_button.grid(row=0, column=2, padx=4)
        ttk.Button(outer, text="ABORT", width=12, command=self.abort_test).grid(row=0, column=3, padx=4, sticky="w")

    def _build_table(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Secuencia de Test", padding=(6, 4))
        frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(4, 4))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ["line", "name", "status", "measured", "low", "high", "unit", "duration"]
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="none")

        headings = {
            "line": "Linea",
            "name": "Nombre del Paso",
            "status": "Estado",
            "measured": "Valor Medido",
            "low": "Limite Inferior",
            "high": "Limite Superior",
            "unit": "Unidad",
            "duration": "Duracion [s]",
        }
        widths = {
            "line": 60,
            "name": 280,
            "status": 110,
            "measured": 130,
            "low": 120,
            "high": 120,
            "unit": 80,
            "duration": 110,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], stretch=column == "name", anchor="center")

        tree_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

    def _build_log(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Consola / Log del sistema", padding=(8, 8))
        frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(frame, height=10, wrap="word", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    def _load_default_program(self) -> None:
        if self.current_program_path.exists():
            self.load_program(self.current_program_path)
        else:
            self._append_log(
                f"No se encontro {self.current_program_path.name} en el directorio del proyecto.",
                level="ERROR",
            )

    def load_program_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            title="Seleccionar Test Program",
            initialdir=str(_PROGRAMS_DIR),
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if selected:
            self.load_program(Path(selected))

    def load_program(self, path: Path) -> None:
        metadata = self.engine.load_program(path)
        self.current_program_path = path
        self.tp_name_var.set(metadata.name)
        self.tp_version_var.set(metadata.version)
        self.tp_file_var.set(path.name)
        self._rebuild_sequence_table()
        self._append_log(f"TP cargado: {metadata.name} v{metadata.version} ({path.name})")

    def _rebuild_sequence_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.row_ids.clear()

        for step in self.engine.program:
            row_id = str(step.line)
            self.row_ids[step.line] = row_id
            self.tree.insert(
                "",
                "end",
                iid=row_id,
                values=(
                    step.line,
                    step.name,
                    StepStatus.PENDING,
                    "",
                    step.low,
                    step.high,
                    step.unit,
                    "",
                ),
            )

    def start_test(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            messagebox.showinfo("Prueba en curso", "Ya hay una prueba ejecutandose.")
            return

        if not self.engine.program:
            messagebox.showerror("Sin TP", "Debe cargar un Test Program antes de iniciar.")
            return

        self.loop_stop_event.clear()
        self.paused = False
        self.pause_button.configure(text="PAUSE")
        self._set_status(_STATUS_LABELS[RunStatus.TESTING], _STATUS_COLORS[RunStatus.TESTING])
        self._rebuild_sequence_table()
        self._append_log("Preparando nueva ejecucion.")

        context = ExecutionContext(
            station_id=self.station_var.get().strip() or "ATE-UNI-01",
            operator_name=self.operator_var.get().strip() or "Operario",
            uut_serial=self.uut_var.get().strip(),
        )
        loop_enabled = self.loop_var.get()

        self.run_thread = threading.Thread(
            target=self._worker_run,
            args=(context, loop_enabled),
            daemon=True,  # el hilo se destruye automáticamente al cerrar la ventana
        )
        self.run_thread.start()

    def _worker_run(self, context: ExecutionContext, loop_enabled: bool) -> None:
        try:
            while not self.loop_stop_event.is_set():
                result = self.engine.run(context=context)
                if not loop_enabled:
                    break
                if result.overall_status != RunStatus.PASS:
                    break
        finally:
            self.event_queue.put({"type": "worker_finished"})

    def toggle_pause(self) -> None:
        if not self.run_thread or not self.run_thread.is_alive():
            return
        self.paused = not self.paused
        self.engine.set_paused(self.paused)
        if self.paused:
            self.pause_button.configure(text="RESUME")
            self._set_status("PAUSED", "#0d6efd")
            self._append_log("Prueba en pausa.")
        else:
            self.pause_button.configure(text="PAUSE")
            self._set_status(_STATUS_LABELS[RunStatus.TESTING], _STATUS_COLORS[RunStatus.TESTING])
            self._append_log("Prueba reanudada.")

    def abort_test(self) -> None:
        if not self.run_thread or not self.run_thread.is_alive():
            self._set_status(_STATUS_LABELS[RunStatus.ABORTED], _STATUS_COLORS[RunStatus.ABORTED])
            return
        self.loop_stop_event.set()
        self.engine.request_stop()
        self._append_log("Solicitud de abort enviada al motor.", level="ERROR")

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

        if event_type == "program_loaded":
            return

        if event_type == "status":
            status = event.get("value", "READY")
            self._set_status(_STATUS_LABELS.get(status, status), _STATUS_COLORS.get(status, "#6c757d"))
            return

        if event_type == "log":
            self._append_log(event.get("message", ""), level=event.get("level", "INFO"), timestamp=event.get("timestamp"))
            return

        if event_type == "step":
            line = event.get("line")
            if line in self.row_ids:
                self.tree.item(
                    self.row_ids[line],
                    values=(
                        line,
                        event.get("name", ""),
                        event.get("status", ""),
                        event.get("measured", ""),
                        event.get("low", ""),
                        event.get("high", ""),
                        event.get("unit", ""),
                        event.get("duration", ""),
                    ),
                )
            return

        if event_type == "prompt":
            accepted = messagebox.askokcancel("Accion manual requerida", event.get("message", ""))
            event["response_queue"].put(accepted)
            return

        if event_type == "run_complete":
            overall = event.get("overall_status", RunStatus.FAIL)
            self._set_status(_STATUS_LABELS.get(overall, overall), _STATUS_COLORS.get(overall, "#6c757d"))
            self._append_log(
                f"Ejecucion completada. Resultado={overall}. Duracion total={event.get('duration_s', 0)} s"
            )
            return

        if event_type in ("paused", "worker_finished"):
            if event_type == "worker_finished":
                self.pause_button.configure(text="PAUSE")
                self.paused = False
            return

    def _set_status(self, text: str, bg: str) -> None:
        self.status_text_var.set(text)
        self.status_frame.configure(bg=bg)
        self.status_label.configure(bg=bg)

    def _append_log(self, message: str, level: str = "INFO", timestamp: str = "LOG") -> None:
        line = f"[{timestamp}] [{level}] {message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
