"""
ToggleRow - modern labeled switch row.
"""

import customtkinter as ctk
from typing import Callable, Optional

TEXT_PRIMARY   = "#e8eaed"
TEXT_SECONDARY = "#8b949e"
ACCENT         = "#0d6efd"


class ToggleRow(ctk.CTkFrame):
    def __init__(
        self,
        master,
        label: str,
        sub_label: str = "",
        default: bool = True,
        on_change: Optional[Callable[[bool], None]] = None,
        indent: int = 0,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._cb = on_change
        self._var = ctk.BooleanVar(value=default)

        self.grid_columnconfigure(0, weight=1)

        lf = ctk.CTkFrame(self, fg_color="transparent")
        lf.grid(row=0, column=0, sticky="w", padx=(indent, 0))

        self._lbl = ctk.CTkLabel(
            lf, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_PRIMARY, anchor="w",
        )
        self._lbl.pack(anchor="w")

        if sub_label:
            ctk.CTkLabel(
                lf, text=sub_label,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_SECONDARY, anchor="w",
                wraplength=280, justify="left",
            ).pack(anchor="w", pady=(1, 0))

        self._sw = ctk.CTkSwitch(
            self, text="", variable=self._var, command=self._fire,
            width=46, height=24,
            progress_color=ACCENT,
        )
        self._sw.grid(row=0, column=1, padx=(12, 0), sticky="e")

    def _fire(self):
        if self._cb:
            self._cb(self._var.get())

    def get(self) -> bool:
        return self._var.get()

    def set(self, v: bool):
        self._var.set(v)

    def set_enabled(self, v: bool):
        self._sw.configure(state="normal" if v else "disabled")
        self._lbl.configure(
            text_color=TEXT_PRIMARY if v else TEXT_SECONDARY
        )
