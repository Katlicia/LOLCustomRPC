"""
Settings Window — LoLCustomRPC.
"""

import logging
import queue
import customtkinter as ctk

logger = logging.getLogger(__name__)
from typing import Callable, Optional

from services.config import ConfigManager
from ui.components.discord_preview import DiscordPreview
from ui.components.toggle_row import ToggleRow
from i18n.translator import Translator

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Palette
BASE    = "#1C1C1F"
SURFACE = "#26262A"
CARD    = "#2E2E33"
BORDER  = "#3A3A40"
BORDER2 = "#44444B"
ACCENT  = "#0d6efd"
ACCENT_DIM = "#0a58ca"
WHITE   = "#e8eaed"
MUTED   = "#9ca3af"
MUTED2  = "#6b7280"
RED     = "#e84057"
GREEN   = "#23a55a"

FONT_UI   = "Segoe UI"
FONT_MONO = "Consolas"


class CollapsibleSection(ctk.CTkFrame):
    """Section header with a collapse/expand toggle."""

    def __init__(self, parent, title: str, expanded: bool = True, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._expanded = expanded

        hdr = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        hdr.pack(fill="x", pady=(0, 0))

        ctk.CTkFrame(hdr, width=3, height=16, fg_color=ACCENT, corner_radius=2).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkLabel(
            hdr, text=title.upper(),
            font=ctk.CTkFont(family=FONT_UI, size=16, weight="bold"),
            text_color=WHITE,
        ).pack(side="left")

        self._arrow = ctk.CTkLabel(
            hdr, text="▾" if expanded else "▸",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        )
        self._arrow.pack(side="left", padx=(8, 0))

        # 16px left indent gives a tree-like hierarchy
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self._body.pack(fill="x", padx=(16, 0), pady=(4, 0))

        hdr.bind("<Button-1>", self._toggle)
        for child in hdr.winfo_children():
            child.bind("<Button-1>", self._toggle)

    def _toggle(self, *_):
        self._expanded = not self._expanded
        if self._expanded:
            self._body.pack(fill="x", padx=(16, 0), pady=(4, 0))
            self._arrow.configure(text="▾")
        else:
            self._body.pack_forget()
            self._arrow.configure(text="▸")

    @property
    def body(self) -> ctk.CTkFrame:
        return self._body


class GUILogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord):
        try:
            self._q.put_nowait(self.format(record))
        except queue.Full:
            pass


class SettingsWindow(ctk.CTk):

    def __init__(self, config: ConfigManager, translator: Optional[Translator] = None, on_close: Optional[Callable] = None):
        super().__init__()
        self._config     = config
        self._translator = translator
        self._on_close   = on_close
        self._pending: dict = {}
        self._log_q: queue.Queue = queue.Queue(maxsize=500)
        self._active = "display"

        self.title("LoLCustomRPC")
        self.geometry("1120x760")
        self.minsize(960, 660)
        self.resizable(True, True)
        self.configure(fg_color=BASE)
        self.protocol("WM_DELETE_WINDOW", self._close)

        handler = GUILogHandler(self._log_q)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s  %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)

        self._build()
        self._load_from_config()
        self._show_nav("display")
        self._poll_logs()

    # Layout

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)   # header + tab bar
        self.grid_rowconfigure(1, weight=1)   # content
        self.grid_rowconfigure(2, weight=0)   # footer

        self._build_header()
        self._build_main()
        self._build_footer()

    # Header + Tab bar

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        # Single row: title | tabs (flex spacer) | status dot
        row = ctk.CTkFrame(hdr, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(14, 0))

        # Status indicators — packed first (side="right") so they anchor to the right edge
        sf = ctk.CTkFrame(row, fg_color="transparent")
        sf.pack(side="right")

        # LoL status
        self._lol_dot = ctk.CTkLabel(sf, text="●", font=ctk.CTkFont(size=15), text_color=RED)
        self._lol_dot.pack(side="left", padx=(0, 4))
        self._lol_lbl = ctk.CTkLabel(
            sf, text="LoL",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        )
        self._lol_lbl.pack(side="left", padx=(0, 16))

        # Discord status
        self._discord_dot = ctk.CTkLabel(sf, text="●", font=ctk.CTkFont(size=15), text_color=RED)
        self._discord_dot.pack(side="left", padx=(0, 4))
        self._discord_lbl = ctk.CTkLabel(
            sf, text="Discord",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        )
        self._discord_lbl.pack(side="left")

        ctk.CTkLabel(
            row, text="LoLCustomRPC",
            font=ctk.CTkFont(family=FONT_UI, size=22, weight="bold"),
            text_color=WHITE,
        ).pack(side="left", padx=(0, 16))

        # Tab buttons immediately right of title
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        nav = [
            ("display", "Display"),
            ("general", "General"),
            ("about",   "About"),
        ]
        for key, label in nav:
            btn = ctk.CTkButton(
                row, text=label,
                font=ctk.CTkFont(family=FONT_UI, size=16),
                fg_color="transparent",
                hover_color=CARD,
                text_color=MUTED,
                corner_radius=6,
                height=36,
                width=110,
                command=lambda k=key: self._show_nav(k),
            )
            btn.pack(side="left", padx=(0, 2))
            self._nav_btns[key] = btn

        # Thin separator under header row
        ctk.CTkFrame(hdr, height=1, fg_color=BORDER).pack(fill="x", pady=(10, 0))

    # Main area

    def _build_main(self):
        self._main = ctk.CTkFrame(self, fg_color=BASE, corner_radius=0)
        self._main.grid(row=1, column=0, sticky="nsew")
        self._main.grid_columnconfigure(0, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

        self._panels: dict[str, ctk.CTkFrame] = {
            "display": self._make_display_panel(),
            "general": self._make_general_panel(),
            "about":   self._make_about_panel(),
        }

    # Footer

    def _build_footer(self):
        ft = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=64)
        ft.grid(row=2, column=0, sticky="ew")
        ft.grid_propagate(False)
        ctk.CTkFrame(ft, height=1, fg_color=BORDER).pack(fill="x", side="top")

        bf = ctk.CTkFrame(ft, fg_color="transparent")
        bf.pack(side="right", padx=20, pady=12)

        ctk.CTkButton(
            bf, text="Cancel", width=110, height=38,
            fg_color="transparent",
            border_width=1, border_color=BORDER2,
            hover_color=CARD,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_UI, size=15),
            command=self._on_cancel,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            bf, text="Save", width=110, height=38,
            fg_color=ACCENT, hover_color=ACCENT_DIM,
            text_color=WHITE,
            font=ctk.CTkFont(family=FONT_UI, size=15, weight="bold"),
            command=self._on_save,
        ).pack(side="left")

    # Panels

    def _make_display_panel(self) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(self._main, fg_color="transparent")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=0, minsize=380)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=0)   # log strip at bottom

        # Declare early - preview init references this var
        self._logo_var = ctk.StringVar(value=self._config.get("display.logo", "lol_logo"))

        # Left: logo selector at top, then toggles
        left = ctk.CTkScrollableFrame(
            panel, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=BORDER2,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(28, 12), pady=(20, 0))

        # Logo section at top of left panel
        sec_logo = CollapsibleSection(left, "Logo", expanded=True)
        sec_logo.pack(fill="x", pady=(0, 4))

        logo_inner = ctk.CTkFrame(sec_logo.body, fg_color="transparent")
        logo_inner.pack(fill="x", pady=(2, 4))

        for val, label in [("lol_logo", "LoL Logo"), ("lol_legacy_logo", "LoL Legacy Logo")]:
            ctk.CTkRadioButton(
                logo_inner, text=label,
                variable=self._logo_var, value=val,
                font=ctk.CTkFont(family=FONT_UI, size=15),
                text_color=WHITE,
                fg_color=ACCENT,
                hover_color=ACCENT_DIM,
                command=self._on_logo_changed,
            ).pack(side="left", padx=(0, 20))

        ctk.CTkFrame(left, height=1, fg_color=BORDER).pack(fill="x", pady=(2, 10))

        # Identity section
        sec2 = CollapsibleSection(left, "Identity", expanded=True)
        sec2.pack(fill="x", pady=(0, 4))

        self._nick_row = ToggleRow(
            sec2.body, label="Show username",
            default=self._config.get("display.show_nick", True),
            on_change=self._on_nick_changed,
        )
        self._nick_row.pack(fill="x", pady=4)

        self._tag_row = ToggleRow(
            sec2.body, label="Show tag  (#TAG)",
            sub_label="Visible only when username is shown.",
            default=self._config.get("display.show_tag", True),
            indent=16,
            on_change=self._on_tag_changed,
        )
        self._tag_row.pack(fill="x", pady=4)

        self._rank_row = ToggleRow(
            sec2.body, label="Show rank",
            default=self._config.get("display.show_rank", True),
            on_change=self._on_rank_changed,
        )
        self._rank_row.pack(fill="x", pady=4)

        self._level_row = ToggleRow(
            sec2.body, label="Show level",
            default=self._config.get("display.show_level", True),
            on_change=self._on_level_changed,
        )
        self._level_row.pack(fill="x", pady=4)

        ctk.CTkFrame(left, height=1, fg_color=BORDER).pack(fill="x", pady=(2, 10))

        sec3 = CollapsibleSection(left, "In Game", expanded=True)
        sec3.pack(fill="x", pady=(0, 4))

        self._kda_row = ToggleRow(
            sec3.body, label="Show KDA",
            default=self._config.get("display.show_kda", True),
            on_change=self._on_kda_changed,
        )
        self._kda_row.pack(fill="x", pady=4)

        ctk.CTkFrame(left, height=1, fg_color=BORDER).pack(fill="x", pady=(2, 10))

        # Language section
        sec_lang = CollapsibleSection(left, "Language", expanded=True)
        sec_lang.pack(fill="x", pady=(0, 4))

        lang_row = ctk.CTkFrame(sec_lang.body, fg_color="transparent")
        lang_row.pack(fill="x", pady=(4, 6))
        lang_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            lang_row, text="RPC Language",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=WHITE,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))

        self._lang_var = ctk.StringVar()
        self._lang_menu = ctk.CTkOptionMenu(
            lang_row,
            values=self._build_lang_values(),
            variable=self._lang_var,
            command=self._on_lang_changed,
            font=ctk.CTkFont(family=FONT_UI, size=14),
            fg_color=CARD,
            button_color=BORDER2,
            button_hover_color=ACCENT,
            dropdown_fg_color=CARD,
            dropdown_hover_color=BORDER2,
            text_color=WHITE,
            width=220, height=34,
            dynamic_resizing=False,
        )
        self._lang_menu.grid(row=0, column=1, sticky="w")
        self._lang_menu.set(
            self._code_to_lang_label(self._config.get("general.language", "auto"))
        )

        self._tag_row.set_enabled(self._nick_row.get())

        # Right: preview card (fills height)
        right = ctk.CTkFrame(panel, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(0, 28), pady=(20, 16))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=0)   # preview
        right.grid_rowconfigure(2, weight=1)   # spacer

        # Preview header
        prev_hdr = ctk.CTkFrame(right, fg_color="transparent")
        prev_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        prev_hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            prev_hdr, text="PREVIEW",
            font=ctk.CTkFont(family=FONT_UI, size=11, weight="bold"),
            text_color=WHITE,
        ).grid(row=0, column=0, sticky="w")

        self._state_var = ctk.StringVar(value="Main Menu")
        ctk.CTkOptionMenu(
            prev_hdr,
            values=["Main Menu", "In Lobby", "Champion Select", "In Game"],
            variable=self._state_var,
            command=self._on_state_changed,
            font=ctk.CTkFont(family=FONT_UI, size=13),
            fg_color=CARD,
            button_color=BORDER2,
            button_hover_color=ACCENT,
            dropdown_fg_color=CARD,
            dropdown_hover_color=BORDER2,
            text_color=WHITE,
            width=170, height=32,
        ).grid(row=0, column=1, sticky="e")

        # Preview card
        self._preview = DiscordPreview(right, translator=self._translator)
        self._preview.grid(row=1, column=0, sticky="ew")
        self._preview.set_state("Main Menu")
        self._preview.set_logo(self._logo_var.get())
        self._preview.set_nick_visible(self._config.get("display.show_nick", True))
        self._preview.set_tag_visible(self._config.get("display.show_tag", True))
        self._preview.set_rank_visible(self._config.get("display.show_rank", True))
        self._preview.set_level_visible(self._config.get("display.show_level", True))
        self._preview.set_kda_visible(self._config.get("display.show_kda", True))

        # Log strip — spans bottom of both columns
        log_strip = ctk.CTkFrame(panel, fg_color=SURFACE, corner_radius=0, height=200)
        log_strip.grid(row=1, column=0, columnspan=1, sticky="nsew", padx=(28, 12), pady=(8, 16))
        log_strip.grid_propagate(False)
        log_strip.grid_columnconfigure(0, weight=1)
        log_strip.grid_rowconfigure(1, weight=1)

        ctk.CTkFrame(log_strip, height=1, fg_color=BORDER).grid(row=0, column=0, sticky="ew")

        log_inner = ctk.CTkFrame(log_strip, fg_color="transparent")
        log_inner.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 8))
        log_inner.grid_columnconfigure(0, weight=1)
        log_inner.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_inner, text="LOG",
            font=ctk.CTkFont(family=FONT_UI, size=13, weight="bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")

        self._log_box = ctk.CTkTextbox(
            log_inner,
            font=ctk.CTkFont(family=FONT_MONO, size=13),
            fg_color=BASE,
            text_color="#6ee7b7",
            border_color=BORDER,
            border_width=1,
            corner_radius=6,
            wrap="none",
            activate_scrollbars=True,
            state="disabled",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

        return panel

    def _make_general_panel(self) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(self._main, fg_color="transparent")
        content = ctk.CTkFrame(panel, fg_color="transparent")
        content.pack(fill="x", padx=28, pady=24)

        sec = CollapsibleSection(content, "Startup", expanded=True)
        sec.pack(fill="x", pady=(0, 8))

        self._autostart_row = ToggleRow(
            sec.body, label="Start with Windows",
            sub_label="Launch automatically at login.",
            default=self._config.get("general.autostart", True),
            on_change=self._on_autostart_changed,
        )
        self._autostart_row.pack(fill="x", pady=4)

        self._minimized_row = ToggleRow(
            sec.body, label="Start minimized to tray",
            sub_label="Skip the window on launch.",
            default=self._config.get("general.start_minimized", True),
            on_change=self._on_minimized_changed,
        )
        self._minimized_row.pack(fill="x", pady=4)

        return panel

    def _make_about_panel(self) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(self._main, fg_color="transparent")

        ctk.CTkLabel(
            panel, text="LoLCustomRPC",
            font=ctk.CTkFont(family=FONT_UI, size=30, weight="bold"),
            text_color=WHITE,
        ).pack(pady=(60, 6))

        ctk.CTkLabel(
            panel, text="Custom Discord Rich Presence for League of Legends",
            font=ctk.CTkFont(family=FONT_UI, size=16),
            text_color=MUTED,
        ).pack()

        ctk.CTkLabel(
            panel, text="v1.0.0",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED2,
        ).pack(pady=(4, 20))

        ctk.CTkFrame(panel, height=1, width=200, fg_color=BORDER).pack()

        ctk.CTkLabel(
            panel, text="github.com/LoL-RPC-Custom",
            font=ctk.CTkFont(family=FONT_UI, size=16),
            text_color=ACCENT,
        ).pack(pady=16)

        return panel

    # Navigation

    def _show_nav(self, key: str):
        for p in self._panels.values():
            p.grid_forget()
            p.pack_forget()
        for k, btn in self._nav_btns.items():
            if k == key:
                btn.configure(
                    fg_color="transparent",
                    text_color=WHITE,
                    font=ctk.CTkFont(family=FONT_UI, size=16, weight="bold"),
                    border_width=0,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=MUTED,
                    font=ctk.CTkFont(family=FONT_UI, size=16, weight="normal"),
                    border_width=0,
                )
        self._panels[key].pack(fill="both", expand=True)
        self._active = key

    # Callbacks

    def _on_nick_changed(self, v: bool):
        logger.info(f"Setting: show_nick = {v}")
        self._mark("display.show_nick", v)
        self._tag_row.set_enabled(v)
        if not v:
            self._tag_row.set(False)
            self._mark("display.show_tag", False)
        self._preview.set_nick_visible(v)
        self._preview.set_tag_visible(self._tag_row.get())

    def _on_tag_changed(self, v: bool):
        logger.info(f"Setting: show_tag = {v}")
        self._mark("display.show_tag", v)
        self._preview.set_tag_visible(v)

    def _on_rank_changed(self, v: bool):
        logger.info(f"Setting: show_rank = {v}")
        self._mark("display.show_rank", v)
        self._preview.set_rank_visible(v)

    def _on_level_changed(self, v: bool):
        logger.info(f"Setting: show_level = {v}")
        self._mark("display.show_level", v)
        self._preview.set_level_visible(v)

    def _on_kda_changed(self, v: bool):
        logger.info(f"Setting: show_kda = {v}")
        self._mark("display.show_kda", v)
        self._preview.set_kda_visible(v)

    def _on_autostart_changed(self, v: bool):
        logger.info(f"Setting: autostart = {v}")
        self._mark("general.autostart", v)

    def _on_minimized_changed(self, v: bool):
        logger.info(f"Setting: start_minimized = {v}")
        self._mark("general.start_minimized", v)

    def _on_logo_changed(self):
        val = self._logo_var.get()
        logger.info(f"Setting: logo = {val}")
        self._mark("display.logo", val)
        self._preview.set_logo(val)

    def _on_state_changed(self, val: str):
        self._preview.set_state(val)

    def _on_lang_changed(self, label: str):
        code = "auto" if label.startswith("auto") else label.rsplit("[", 1)[-1].rstrip("]").strip()
        logger.info(f"Setting: language = {code}")
        self._mark("general.language", code)
        if self._translator:
            target = self._translator.auto_locale if code == "auto" else code
            self._translator.set_locale(target)
            if hasattr(self, "_preview"):
                self._preview.set_translator(self._translator)

    @staticmethod
    def _build_lang_values() -> list[str]:
        import os, json
        from i18n.translator import LOL_LOCALE_MAP
        locales_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "i18n", "locales",
        )
        entries = ["auto (LoL Client)"]
        for code in sorted(set(LOL_LOCALE_MAP.values())):
            path = os.path.join(locales_dir, f"{code}.json")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                native = meta.get("_native_name", code)
                entries.append(f"{native}  [{code}]")
            except Exception:
                entries.append(code)
        return entries

    def _code_to_lang_label(self, code: str) -> str:
        if code == "auto":
            return "auto (LoL Client)"
        for label in self._build_lang_values():
            if label.endswith(f"[{code}]"):
                return label
        return "auto (LoL Client)"

    # Save / Cancel

    def _mark(self, key: str, value):
        self._pending[key] = value

    def _load_from_config(self):
        self._pending = {}

    def _on_save(self):
        for key, value in self._pending.items():
            self._config.set(key, value)
        if self._pending:
            logger.info(f"Config saved: {self._pending}")
            self._config.save()
        self._pending = {}

    def _on_cancel(self):
        self._pending = {}
        if hasattr(self, "_nick_row"):
            self._nick_row.set(self._config.get("display.show_nick", True))
            self._tag_row.set(self._config.get("display.show_tag", True))
            self._rank_row.set(self._config.get("display.show_rank", True))
            self._level_row.set(self._config.get("display.show_level", True))
            if hasattr(self, "_kda_row"):
                self._kda_row.set(self._config.get("display.show_kda", True))
            self._tag_row.set_enabled(self._nick_row.get())
        if hasattr(self, "_autostart_row"):
            self._autostart_row.set(self._config.get("general.autostart", True))
            self._minimized_row.set(self._config.get("general.start_minimized", True))
        if hasattr(self, "_logo_var"):
            self._logo_var.set(self._config.get("display.logo", "lol_logo"))
            self._preview.set_logo(self._logo_var.get())
        if hasattr(self, "_preview"):
            self._preview.set_nick_visible(self._nick_row.get())
            self._preview.set_tag_visible(self._tag_row.get())
            self._preview.set_rank_visible(self._rank_row.get())
            self._preview.set_level_visible(self._level_row.get())
            if hasattr(self, "_kda_row"):
                self._preview.set_kda_visible(self._kda_row.get())
        if hasattr(self, "_lang_menu"):
            self._lang_menu.set(
                self._code_to_lang_label(self._config.get("general.language", "auto"))
            )

    # Status

    def set_discord_status(self, connected: bool):
        if hasattr(self, "_discord_dot"):
            self._discord_dot.configure(text_color=GREEN if connected else RED)

    def set_lol_status(self, connected: bool):
        if hasattr(self, "_lol_dot"):
            self._lol_dot.configure(text_color=GREEN if connected else RED)

    # Log polling

    def _poll_logs(self):
        MAX_LINES = 300
        try:
            msgs = []
            while True:
                msgs.append(self._log_q.get_nowait())
        except queue.Empty:
            pass

        if msgs and hasattr(self, "_log_box"):
            self._log_box.configure(state="normal")
            for m in msgs:
                self._log_box.insert("end", m + "\n")
            lines = self._log_box.get("1.0", "end").split("\n")
            if len(lines) > MAX_LINES:
                self._log_box.delete("1.0", f"{len(lines) - MAX_LINES}.0")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

        self.after(200, self._poll_logs)

    # Close

    def _close(self):
        self.withdraw()
        if self._on_close:
            self._on_close()
