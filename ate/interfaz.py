import logging
import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from ate import config
from ate.motor import Motor
from ate.programa import cargar_programa
from ate.reporte import guardar_reporte

BLANCO = "#ffffff"
GRIS_CLARO = "#e9ecef"
GRIS = "#adb5bd"
TEXTO = "#212529"
TEXTO_SUAVE = "#6c757d"
AZUL = "#0d6efd"
AZUL_OSCURO = "#0a58ca"
VERDE = "#198754"
ROJO = "#dc3545"


class Aplicacion:
    """Ventana del operario: elegir un TP, presionar START y ver el avance en la barra.

    La barra termina verde (PASS) o roja (FAIL / ABORTADO). Los errores van a la consola
    y el detalle de cada paso queda en el reporte, que se abre solo al terminar.
    """

    def __init__(self, ventana: tk.Tk):
        self.ventana = ventana
        self.cola = queue.Queue()
        self.programas = {ruta.name: ruta for ruta in sorted(config.CARPETA_PROGRAMAS.glob("*.csv"))}
        self.motor = Motor(al_avanzar=self._al_avanzar, preguntar=self._preguntar_al_operario)

        self._configurar_estilos()
        self._construir_ventana()
        self._atender_cola()

    def _configurar_estilos(self):
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure(".", background=BLANCO, foreground=TEXTO, font=("Segoe UI", 10))
        estilo.configure("Titulo.TLabel", font=("Segoe UI Semibold", 18))
        estilo.configure("Subtitulo.TLabel", foreground=TEXTO_SUAVE)
        estilo.configure("TCombobox", padding=5, background=BLANCO, bordercolor=GRIS, lightcolor=BLANCO, darkcolor=BLANCO)
        estilo.map(
            "TCombobox",
            fieldbackground=[("readonly", BLANCO)],
            selectbackground=[("readonly", BLANCO)],
            selectforeground=[("readonly", TEXTO)],
        )

        # En el tema clam el botón tiene fondo, borde y dos bordes de relieve: se pintan
        # todos del mismo color para que se vea plano.
        estilo.configure(
            "Start.TButton",
            foreground="white",
            font=("Segoe UI Semibold", 10),
            padding=(22, 6),
            background=AZUL,
            bordercolor=AZUL,
            lightcolor=AZUL,
            darkcolor=AZUL,
        )
        colores = [("disabled", GRIS), ("active", AZUL_OSCURO)]
        estilo.map(
            "Start.TButton",
            foreground=[("disabled", "white")],
            background=colores,
            bordercolor=colores,
            lightcolor=colores,
            darkcolor=colores,
        )

        for nombre, color in [("Azul", AZUL), ("Verde", VERDE), ("Rojo", ROJO)]:
            estilo.configure(
                f"{nombre}.Horizontal.TProgressbar",
                thickness=26,
                background=color,
                lightcolor=color,
                darkcolor=color,
                troughcolor=GRIS_CLARO,
                bordercolor=GRIS_CLARO,
            )

    def _construir_ventana(self):
        self.ventana.title("Test Executive - RIGOL DS1202Z-E + DG1022Z")
        self.ventana.configure(background=BLANCO)
        self.ventana.resizable(False, False)

        marco = ttk.Frame(self.ventana, padding=24)
        marco.pack(fill="both", expand=True)

        encabezado = ttk.Frame(marco)
        encabezado.pack(fill="x")
        # Se guarda en self: si la imagen queda solo en una variable local, Python la libera y no se ve.
        self.logo = tk.PhotoImage(file=config.LOGO).subsample(5)  # 800x357 px -> 160x71 px
        ttk.Label(encabezado, image=self.logo).pack(side="left")
        titulos = ttk.Frame(encabezado)
        titulos.pack(side="left", padx=(20, 0))
        ttk.Label(titulos, text="Test Executive", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(titulos, text="Medidas Electrónicas II  ·  RIGOL DS1202Z-E + DG1022Z", style="Subtitulo.TLabel").pack(anchor="w")

        ttk.Separator(marco).pack(fill="x", pady=20)

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Test Program").pack(side="left")
        self.boton_start = ttk.Button(fila, text="START", style="Start.TButton", command=self.iniciar_prueba)
        self.boton_start.pack(side="right")
        self.selector = ttk.Combobox(fila, values=list(self.programas), state="readonly", width=40)
        self.selector.pack(side="left", fill="x", expand=True, padx=12)

        self.barra = ttk.Progressbar(marco, style="Azul.Horizontal.TProgressbar")
        self.barra.pack(fill="x", pady=(20, 0))

        if self.programas:
            self.selector.current(0)
        else:
            logging.error("No hay TP (*.csv) en %s", config.CARPETA_PROGRAMAS)

    def iniciar_prueba(self):
        ruta = self.programas.get(self.selector.get())
        if ruta is None:
            logging.error("No hay ningún TP seleccionado.")
            return
        try:
            programa = cargar_programa(ruta)
        except Exception as error:
            logging.error("No se pudo cargar %s: %s", ruta.name, error)
            return

        self.boton_start.state(["disabled"])
        self.barra.configure(style="Azul.Horizontal.TProgressbar", value=0, maximum=len(programa.pasos))
        threading.Thread(target=self._correr_prueba, args=(programa,), daemon=True).start()

    def _correr_prueba(self, programa):
        """Corre en un hilo aparte para que la ventana no se congele mientras dura la prueba."""
        try:
            resultado = self.motor.ejecutar(programa)
            reporte = guardar_reporte(programa, resultado)
            self._en_la_ui(lambda: self._mostrar_resultado(resultado.estado, reporte))
        except Exception:
            logging.exception("Error inesperado durante la prueba.")
            self._en_la_ui(lambda: self._mostrar_resultado("FAIL", None))

    def _mostrar_resultado(self, estado, reporte):
        color = "Verde" if estado == "PASS" else "Rojo"
        self.barra.configure(style=f"{color}.Horizontal.TProgressbar", value=self.barra["maximum"])
        self.boton_start.state(["!disabled"])
        if reporte:
            abrir_archivo(reporte)

    # tkinter no es thread-safe: el hilo de la prueba nunca toca la ventana directamente,
    # sino que deja funciones en la cola y la ventana las ejecuta cada 100 ms.
    def _en_la_ui(self, funcion):
        self.cola.put(funcion)

    def _atender_cola(self):
        try:
            while not self.cola.empty():
                tarea = self.cola.get()
                tarea()
        finally:
            self.ventana.after(100, self._atender_cola)

    def _al_avanzar(self, actual, total):
        self._en_la_ui(lambda: self.barra.configure(value=actual, maximum=total))

    def _preguntar_al_operario(self, mensaje):
        respuesta = queue.Queue()
        self._en_la_ui(
            lambda: respuesta.put(messagebox.askokcancel("Acción manual requerida", mensaje, parent=self.ventana))
        )
        return respuesta.get()  # el hilo de la prueba espera acá hasta que el operario responda


def abrir_archivo(ruta: Path):
    try:
        os.startfile(ruta)  # Windows
    except AttributeError:
        webbrowser.open(ruta.as_uri())  # Linux / macOS
    except OSError as error:
        logging.error("No se pudo abrir %s: %s", ruta, error)


def iniciar():
    ventana = tk.Tk()
    Aplicacion(ventana)
    ventana.mainloop()
