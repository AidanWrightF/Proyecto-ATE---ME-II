from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from instruments import InstrumentConfig, SUPPORTED_SCOPE_MODELS, list_visa_resources as discover_visa_resources
from te_engine import ExecutionContext, TestExecutiveEngine


class TEOperatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Test Executive - DDS / Osciloscopio")
        self.root.geometry("1280x840")
        self.root.minsize(1100, 740)

        self.base_dir = Path(__file__).resolve().parent
        self.event_queue: queue.Queue = queue.Queue()
        self.engine = TestExecutiveEngine(
            event_callback=self._enqueue_event,
            prompt_handler=self._prompt_operator,
        )
        self.run_thread: threading.Thread | None = None
        self.loop_stop_event = threading.Event()
        self.current_program_path = self.base_dir / "tp_ejemplo.csv"
        self.row_ids: dict[int, str] = {}
        self.paused = False

        self._build_variables()
        self._build_ui()
        self._load_default_program()
        self.root.after(100, self._process_events)

    def _build_variables(self) -> None:
        self.tp_name_var = tk.StringVar(value="TP no cargado")
        self.tp_version_var = tk.StringVar(value="0.0")
        self.tp_file_var = tk.StringVar(value=self.current_program_path.name)
        self.station_var = tk.StringVar(value="ATE-UNI-01")
        self.operator_var = tk.StringVar(value="Operario")
        self.uut_var = tk.StringVar()
        self.loop_var = tk.BooleanVar(value=False)
        self.mock_var = tk.BooleanVar(value=True)
        self.scope_model_var = tk.StringVar(value="AUTO")
        self.scope_resource_var = tk.StringVar()
        self.generator_resource_var = tk.StringVar()
        self.status_text_var = tk.StringVar(value="READY")

    def _build_ui(self) -> None:
        self.root.configure(bg="#dfe4ea")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
        self.root.rowconfigure(4, weight=1)

        self._build_top_bar()
        self._build_status_panel()
        self._build_controls()
        self._build_table()
        self._build_log()

    def _build_top_bar(self) -> None:
        top = ttk.Frame(self.root, padding=(10, 10))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(3, weight=1)
        top.columnconfigure(7, weight=1)

        ttk.Label(top, text="TP:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Label(top, textvariable=self.tp_name_var, width=28).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Version:").grid(row=0, column=2, sticky="w", padx=(10, 4))
        ttk.Label(top, textvariable=self.tp_version_var, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(top, text="Estacion:").grid(row=0, column=4, sticky="w", padx=(10, 4))
        ttk.Entry(top, textvariable=self.station_var, width=16).grid(row=0, column=5, sticky="w")
        ttk.Label(top, text="Operario:").grid(row=0, column=6, sticky="w", padx=(10, 4))
        ttk.Entry(top, textvariable=self.operator_var, width=18).grid(row=0, column=7, sticky="w")

        ttk.Label(top, text="Codigo / Serie UUT:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        uut_entry = ttk.Entry(top, textvariable=self.uut_var, width=44)
        uut_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(10, 0))
        uut_entry.focus_set()

        ttk.Checkbutton(top, text="Loop", variable=self.loop_var).grid(row=1, column=4, sticky="w", pady=(10, 0))
        ttk.Checkbutton(top, text="Mock VISA", variable=self.mock_var).grid(row=1, column=5, sticky="w", pady=(10, 0))
        ttk.Button(top, text="Cargar TP", command=self.load_program_dialog).grid(
            row=1, column=6, padx=(10, 4), pady=(10, 0), sticky="ew"
        )
        ttk.Label(top, textvariable=self.tp_file_var).grid(
            row=1, column=7, sticky="w", pady=(10, 0)
        )

        ttk.Label(top, text="Tipo scope:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(
            top,
            textvariable=self.scope_model_var,
            values=SUPPORTED_SCOPE_MODELS,
            width=22,
            state="readonly",
        ).grid(row=2, column=1, sticky="w", pady=(10, 0))

        ttk.Label(top, text="Scope VISA:").grid(row=2, column=2, sticky="w", padx=(10, 4), pady=(10, 0))
        ttk.Entry(top, textvariable=self.scope_resource_var).grid(
            row=2,
            column=3,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        ttk.Button(top, text="Listar VISA", command=self.list_visa_resources).grid(
            row=2,
            column=6,
            columnspan=2,
            padx=(10, 0),
            pady=(10, 0),
            sticky="ew",
        )

        ttk.Label(top, text="Generador VISA:").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(top, textvariable=self.generator_resource_var).grid(
            row=3,
            column=1,
            columnspan=7,
            sticky="ew",
            pady=(10, 0),
        )

    def _build_status_panel(self) -> None:
        self.status_frame = tk.Frame(self.root, bg="#6c757d", height=160)
        self.status_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        self.status_frame.grid_propagate(False)
        self.status_frame.columnconfigure(0, weight=1)
        self.status_frame.rowconfigure(0, weight=1)

        self.status_label = tk.Label(
            self.status_frame,
            textvariable=self.status_text_var,
            bg="#6c757d",
            fg="white",
            font=("Segoe UI", 34, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="nsew")

    def _build_controls(self) -> None:
        controls = ttk.Frame(self.root, padding=(10, 10))
        controls.grid(row=2, column=0, sticky="ew")

        self.start_button = tk.Button(
            controls,
            text="START",
            width=12,
            bg="#198754",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            command=self.start_test,
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.pause_button = tk.Button(
            controls,
            text="PAUSE",
            width=12,
            bg="#ffc107",
            fg="black",
            font=("Segoe UI", 12, "bold"),
            command=self.toggle_pause,
        )
        self.pause_button.pack(side="left", padx=(0, 8))

        self.abort_button = tk.Button(
            controls,
            text="STOP / ABORT",
            width=14,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            command=self.abort_test,
        )
        self.abort_button.pack(side="left")

    def _build_table(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Secuencia de pruebas", padding=(8, 8))
        frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("line", "name", "status", "measured", "low", "high", "unit", "duration")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headings = {
            "line": "#",
            "name": "Nombre del Test",
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
            self._append_log("No se encontro tp_ejemplo.csv en el directorio del proyecto.", level="ERROR")

    def load_program_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            title="Seleccionar Test Program",
            initialdir=str(self.base_dir),
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
                    "Pending",
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
        self._set_status("TESTING...", "#d97706")
        self._rebuild_sequence_table()
        self._append_log("Preparando nueva ejecucion.")

        scope_resource = self.scope_resource_var.get().strip()
        generator_resource = self.generator_resource_var.get().strip()
        scope_model = self.scope_model_var.get().strip() or "AUTO"
        if not self.mock_var.get():
            if not scope_resource:
                messagebox.showerror(
                    "Instrumentos sin configurar",
                    "En modo real debe completar Scope VISA. "
                    "Use un recurso USB/ASRL como 'USB0::...::INSTR' o 'ASRL4::INSTR'. "
                    "Generador VISA es opcional para TPs que solo miden el osciloscopio.",
                )
                return

        context = ExecutionContext(
            station_id=self.station_var.get().strip() or "ATE-UNI-01",
            operator_name=self.operator_var.get().strip() or "Operario",
            uut_serial=self.uut_var.get().strip(),
        )
        instrument_config = InstrumentConfig(
            mock_mode=self.mock_var.get(),
            scope_resource=scope_resource,
            generator_resource=generator_resource,
            scope_model=scope_model,
        )
        loop_enabled = self.loop_var.get()

        self.run_thread = threading.Thread(
            target=self._worker_run,
            args=(context, instrument_config, loop_enabled),
            daemon=True,
        )
        self.run_thread.start()

    def _worker_run(
        self,
        context: ExecutionContext,
        instrument_config: InstrumentConfig,
        loop_enabled: bool,
    ) -> None:
        try:
            while not self.loop_stop_event.is_set():
                result = self.engine.run(context=context, instrument_config=instrument_config)
                if not loop_enabled:
                    break
                if result.overall_status != "PASS":
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
            self._set_status("TESTING...", "#d97706")
            self._append_log("Prueba reanudada.")

    def abort_test(self) -> None:
        if not self.run_thread or not self.run_thread.is_alive():
            self._set_status("ABORTED", "#dc3545")
            return
        self.loop_stop_event.set()
        self.engine.request_stop()
        self._append_log("Solicitud de abort enviada al motor.", level="ERROR")

    def list_visa_resources(self) -> None:
        try:
            resources = discover_visa_resources()
        except Exception as exc:
            self._append_log(f"No se pudieron listar recursos VISA: {exc}", level="ERROR")
            return

        if not resources:
            self._append_log("No se detectaron recursos VISA.", level="ERROR")
            return

        self._append_log("Recursos VISA detectados: " + ", ".join(resources))
        if len(resources) == 1 and not self.scope_resource_var.get().strip():
            self.scope_resource_var.set(resources[0])
            self._append_log(f"Scope VISA sugerido: {resources[0]}")

    def _enqueue_event(self, event: dict) -> None:
        self.event_queue.put(event)

    def _prompt_operator(self, message: str) -> bool:
        response_queue: queue.Queue = queue.Queue(maxsize=1)
        self.event_queue.put({"type": "prompt", "message": message, "response_queue": response_queue})
        return bool(response_queue.get())

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
            colors = {
                "TESTING": "#d97706",
                "PASS": "#198754",
                "FAIL": "#dc3545",
                "ABORTED": "#dc3545",
            }
            labels = {
                "TESTING": "TESTING...",
                "PASS": "PASS",
                "FAIL": "FAIL",
                "ABORTED": "ABORTED",
            }
            self._set_status(labels.get(status, status), colors.get(status, "#6c757d"))
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
            overall = event.get("overall_status", "FAIL")
            if overall == "PASS":
                self._set_status("PASS", "#198754")
            elif overall == "FAIL":
                self._set_status("FAIL", "#dc3545")
            else:
                self._set_status("ABORTED", "#dc3545")
            self._append_log(
                f"Ejecucion completada. Resultado={overall}. Duracion total={event.get('duration_s', 0)} s"
            )
            return

        if event_type == "paused":
            return

        if event_type == "worker_finished":
            self.pause_button.configure(text="PAUSE")
            self.paused = False
            return

    def _set_status(self, text: str, bg: str) -> None:
        self.status_text_var.set(text)
        self.status_frame.configure(bg=bg)
        self.status_label.configure(bg=bg)

    def _append_log(self, message: str, level: str = "INFO", timestamp: str | None = None) -> None:
        timestamp = timestamp or "LOG"
        line = f"[{timestamp}] [{level}] {message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    app = TEOperatorApp(root)
    del app
    root.mainloop()


if __name__ == "__main__":
    main()
