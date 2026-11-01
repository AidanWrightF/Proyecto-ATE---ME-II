from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from ate.ui.operator_app import TEOperatorApp


def main() -> None:
    # Los mensajes de error/log van a la consola (el operario no la ve); nunca a la UI.
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    TEOperatorApp(root)
    root.mainloop()
