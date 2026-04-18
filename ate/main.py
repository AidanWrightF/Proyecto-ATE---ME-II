from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ate.ui.operator_app import TEOperatorApp


def main() -> None:
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    TEOperatorApp(root)
    root.mainloop()
