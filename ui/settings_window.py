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

    def __init__(self, config: ConfigManager, translator: Optional[Translator] = None, on_close: Optional[Callable] = None, app_version: str = "", on_pause_toggle: Optional[Callable] = None, is_paused_fn: Optional[Callable] = None):
        super().__init__()
        self._config         = config
        self._translator     = translator
        self._on_close       = on_close
        self._app_version    = app_version
        self._on_pause_toggle = on_pause_toggle
        self._is_paused_fn   = is_paused_fn
        self._pending: dict = {}
        self._log_q: queue.Queue = queue.Queue(maxsize=500)
        self._active = "display"

        self.title("LoLCustomRPC")
        w, h = 1120, 760
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        import os as _os
        _ico = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "assets", "winicon.ico")
        if _os.path.exists(_ico):
            self.iconbitmap(_ico)
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
        # Start breathe animation for both dots at their initial red color
        self.after(100, lambda: self._start_breathe(self._lol_dot, RED))
        self.after(150, lambda: self._start_breathe(self._discord_dot, RED))
        # One-time welcome popup
        if not self._config.get("general.shown_welcome", False):
            self.after(500, self._show_welcome)

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

        import os as _os
        from PIL import Image as _Image

        # Single row: icon | tabs | (spacer) | status dots + bug button
        row = ctk.CTkFrame(hdr, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(8, 0))

        # Icon — leftmost
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "assets", "icon.png")
        _icon_img = ctk.CTkImage(_Image.open(_icon_path), size=(180, 60))
        ctk.CTkLabel(row, text="", image=_icon_img).pack(side="left", padx=(0, 8))

        # Status indicators + bug button — all anchored to the right edge
        sf = ctk.CTkFrame(row, fg_color="transparent")
        sf.pack(side="right")

        # Discord status
        self._discord_dot = ctk.CTkLabel(sf, text="●", font=ctk.CTkFont(size=15), text_color=RED)
        self._discord_dot.pack(side="left", padx=(0, 4))
        self._discord_lbl = ctk.CTkLabel(
            sf, text="Discord",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        )
        self._discord_lbl.pack(side="left", padx=(0, 12))

        # LoL status
        self._lol_dot = ctk.CTkLabel(sf, text="●", font=ctk.CTkFont(size=15), text_color=RED)
        self._lol_dot.pack(side="left", padx=(0, 4))
        self._lol_lbl = ctk.CTkLabel(
            sf, text="LoL",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        )
        self._lol_lbl.pack(side="left", padx=(0, 12))

        # Bug report button — rightmost
        _bug_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "assets", "78946.png")
        _bug_img = ctk.CTkImage(_Image.open(_bug_path), size=(14, 14))
        bug_btn = ctk.CTkLabel(sf, text="", image=_bug_img, cursor="hand2")
        bug_btn.pack(side="left")
        bug_btn.bind("<Button-1>", lambda _e: __import__("webbrowser").open("https://github.com/Katlicia/LOLCustomRPC/issues/new"))

        # Tab buttons — between icon and right cluster
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        nav = [
            ("display",  "Display"),
            ("general",  "General"),
            ("updates",  "Updates"),
            ("about",    "About"),
        ]
        for key, label in nav:
            btn = ctk.CTkButton(
                row, text=label,
                font=ctk.CTkFont(family=FONT_UI, size=13),
                fg_color="transparent",
                hover_color=CARD,
                text_color=MUTED,
                corner_radius=6,
                height=28,
                width=90,
                command=lambda k=key: self._show_nav(k),
            )
            btn.pack(side="left", padx=(0, 2))
            self._nav_btns[key] = btn

        # Thin separator under header
        ctk.CTkFrame(hdr, height=1, fg_color=BORDER).pack(fill="x", pady=(6, 0))

    # Main area

    def _build_main(self):
        self._main = ctk.CTkFrame(self, fg_color=BASE, corner_radius=0)
        self._main.grid(row=1, column=0, sticky="nsew")
        self._main.grid_columnconfigure(0, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

        self._panels: dict[str, ctk.CTkFrame] = {
            "display": self._make_display_panel(),
            "general": self._make_general_panel(),
            "updates": self._make_updates_panel(),
            "about":   self._make_about_panel(),
        }

    # Footer

    def _build_footer(self):
        ft = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=64)
        ft.grid(row=2, column=0, sticky="ew")
        ft.grid_propagate(False)
        ctk.CTkFrame(ft, height=1, fg_color=BORDER).pack(fill="x", side="top")

        ctk.CTkLabel(
            ft, text=f"Version - {self._app_version}",
            font=ctk.CTkFont(family=FONT_UI, size=16),
            text_color=MUTED2,
        ).pack(side="left", padx=20, pady=12)

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

        self._role_row = ToggleRow(
            sec3.body, label="Show Role",
            default=self._config.get("display.show_role", True),
            on_change=self._on_role_changed,
        )
        self._role_row.pack(fill="x", pady=4)

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
        self._preview.set_role_visible(self._config.get("display.show_role", True))

        # Pause controls below preview
        pause_bar = ctk.CTkFrame(right, fg_color="transparent")
        pause_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        pause_bar.grid_columnconfigure(0, weight=1)

        self._status_dot = ctk.CTkLabel(
            pause_bar, text="● RPC Active",
            font=ctk.CTkFont(family=FONT_UI, size=13),
            text_color=GREEN,
        )
        self._status_dot.grid(row=0, column=0, sticky="w")

        self._pause_btn = ctk.CTkButton(
            pause_bar,
            text="Pause RPC",
            command=self._toggle_pause,
            font=ctk.CTkFont(family=FONT_UI, size=13),
            fg_color=CARD,
            hover_color=BORDER2,
            text_color=WHITE,
            border_width=1,
            border_color=BORDER2,
            width=120, height=30,
            corner_radius=6,
        )
        self._pause_btn.grid(row=0, column=1, sticky="e")
        self._sync_pause_ui()

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

        ctk.CTkFrame(content, height=1, fg_color=BORDER).pack(fill="x", pady=(6, 10))

        sec_upd = CollapsibleSection(content, "Updates", expanded=True)
        sec_upd.pack(fill="x", pady=(0, 8))

        self._auto_update_row = ToggleRow(
            sec_upd.body, label="Auto update",
            sub_label="Download and install updates automatically.",
            default=self._config.get("general.auto_update", True),
            on_change=self._on_auto_update_changed,
        )
        self._auto_update_row.pack(fill="x", pady=4)

        return panel

    def _make_updates_panel(self) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(self._main, fg_color="transparent")
        content = ctk.CTkFrame(panel, fg_color="transparent")
        content.pack(expand=True)

        ctk.CTkLabel(
            content, text="Updates",
            font=ctk.CTkFont(family=FONT_UI, size=26, weight="bold"),
            text_color=WHITE,
        ).pack(pady=(40, 4))

        version_text = f"Current version: v{self._app_version}" if self._app_version else "v1.0.0"
        ctk.CTkLabel(
            content, text=version_text,
            font=ctk.CTkFont(family=FONT_UI, size=14),
            text_color=MUTED2,
        ).pack(pady=(0, 20))

        self._update_btn = ctk.CTkButton(
            content, text="Check for Updates",
            width=180, height=36,
            fg_color=CARD, hover_color=BORDER2,
            border_width=1, border_color=BORDER2,
            text_color=WHITE,
            font=ctk.CTkFont(family=FONT_UI, size=14),
            command=self._on_check_update,
        )
        self._update_btn.pack(pady=(0, 8))

        self._update_label = ctk.CTkLabel(
            content, text="",
            font=ctk.CTkFont(family=FONT_UI, size=13),
            text_color=MUTED,
        )
        self._update_label.pack()

        self._notes_box = ctk.CTkTextbox(
            content,
            width=420, height=120,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT_UI, size=13),
            wrap="word",
            state="disabled",
        )
        self._notes_box.pack(pady=(10, 0))
        self._notes_box.pack_forget()

        # Fetch latest release notes in background on panel creation
        self._fetch_latest_notes()

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

        version_text = f"v{self._app_version}" if self._app_version else "v1.0.0"
        ctk.CTkLabel(
            panel, text=version_text,
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED2,
        ).pack(pady=(4, 20))

        ctk.CTkFrame(panel, height=1, width=200, fg_color=BORDER).pack()

        link = ctk.CTkLabel(
            panel, text="github.com/Katlicia/LOLCustomRPC",
            font=ctk.CTkFont(family=FONT_UI, size=16),
            text_color=ACCENT,
            cursor="hand2",
        )
        link.pack(pady=(16, 4))
        link.bind("<Button-1>", lambda _e: __import__("webbrowser").open("https://github.com/Katlicia/LOLCustomRPC"))

        ctk.CTkLabel(
            panel, text="Discord: yapamiyom.",
            font=ctk.CTkFont(family=FONT_UI, size=15),
            text_color=MUTED,
        ).pack(pady=(0, 16))

        return panel

    def _show_update_notes(self, info) -> None:
        """Fill and reveal the release notes box."""
        notes = info.notes.strip() if info.notes else ""
        if not notes:
            self._notes_box.pack_forget()
            return
        self._notes_box.configure(state="normal")
        self._notes_box.delete("1.0", "end")
        self._notes_box.insert("end", f"What's new in v{info.version}:\n\n{notes}")
        self._notes_box.configure(state="disabled")
        self._notes_box.pack(pady=(10, 0))

    def _fetch_latest_notes(self) -> None:
        """Fetch the latest release notes from GitHub and always show them."""
        import threading
        from services.updater import check_for_update, _parse_version

        def _run():
            info = check_for_update("0.0.0")  # version 0.0.0 ensures latest is always returned
            if info:
                def _show():
                    self._show_update_notes(info)
                    # Set label only if no other check has filled it yet
                    if not self._update_label.cget("text"):
                        up_to_date = _parse_version(info.version) <= _parse_version(self._app_version or "0.0.0")
                        if up_to_date:
                            self._update_label.configure(
                                text=f"You're on the latest version (v{self._app_version}).",
                                text_color=MUTED,
                            )
                self.after(0, _show)

        threading.Thread(target=_run, daemon=True).start()

    def notify_update(self, info) -> None:
        """Called from background thread when a new version is found at startup."""
        auto = self._config.get("general.auto_update", True)

        def _do():
            # Mark the Updates tab button so user notices without opening it
            self._nav_btns["updates"].configure(text="Updates ●", text_color="#4ade80")

            self._show_update_notes(info)

            if auto:
                self._update_label.configure(
                    text=f"v{info.version} available — installing...",
                    text_color="#4ade80",
                )
                self._update_btn.configure(
                    text=f"Installing v{info.version}...",
                    fg_color=ACCENT, hover_color=ACCENT_DIM,
                    state="disabled",
                    command=lambda: self._on_install_update(info),
                )
                self._on_install_update(info)
            else:
                self._update_label.configure(
                    text=f"v{info.version} available — auto update is off.",
                    text_color="#facc15",
                )
                self._update_btn.configure(
                    text=f"Download v{info.version}",
                    fg_color=CARD, hover_color=BORDER2,
                    command=lambda: self._on_install_update(info),
                )
        self.after(0, _do)

    def _on_check_update(self) -> None:
        from services.updater import check_for_update
        self._update_btn.configure(text="Checking...", state="disabled")
        self._update_label.configure(text="", text_color=MUTED)
        self._notes_box.pack_forget()

        def _run():
            info = check_for_update(self._app_version or "0.0.0")
            def _done():
                self._update_btn.configure(state="normal")
                if info:
                    self._update_label.configure(
                        text=f"v{info.version} available!",
                        text_color="#4ade80",
                    )
                    self._update_btn.configure(
                        text=f"Download v{info.version}",
                        fg_color=ACCENT, hover_color=ACCENT_DIM,
                        command=lambda: self._on_install_update(info),
                    )
                    self._show_update_notes(info)
                else:
                    self._update_label.configure(text="You're up to date.", text_color=MUTED)
                    self._update_btn.configure(text="Check for Updates", fg_color=CARD, hover_color=BORDER2)
            self.after(0, _done)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _on_install_update(self, info) -> None:
        import webbrowser, sys
        from tkinter import messagebox
        from services.updater import download_and_install

        # Source mode: open browser, no local install possible
        if not getattr(sys, "frozen", False):
            webbrowser.open(info.release_url)
            return

        auto = self._config.get("general.auto_update", True)
        if not auto:
            msg = (
                f"v{info.version} is available.\n\n"
                f"Auto update is off — do you want to install it now?\n"
                f"The app will restart after the update."
            )
            if not messagebox.askyesno("Update", msg, parent=self):
                self._update_btn.configure(
                    text=f"Download v{info.version}",
                    fg_color=CARD, hover_color=BORDER2,
                    state="normal",
                )
                return

        self._update_btn.configure(text="Downloading... 0%", state="disabled")

        def _progress(pct: int):
            self.after(0, lambda: self._update_btn.configure(text=f"Downloading... {pct}%"))

        def _error(msg: str):
            self.after(0, lambda: [
                self._update_btn.configure(text="Download failed", state="normal"),
                self._update_label.configure(text=msg, text_color="#f87171"),
            ])

        download_and_install(info, on_progress=_progress, on_error=_error)

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

    def _on_role_changed(self, v: bool):
        logger.info(f"Setting: show_role = {v}")
        self._mark("display.show_role", v)
        self._preview.set_role_visible(v)

    def _on_auto_update_changed(self, v: bool):
        logger.info(f"Setting: auto_update = {v}")
        self._mark("general.auto_update", v)

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
            if hasattr(self, "_role_row"):
                self._role_row.set(self._config.get("display.show_role", True))
            self._tag_row.set_enabled(self._nick_row.get())
        if hasattr(self, "_autostart_row"):
            self._autostart_row.set(self._config.get("general.autostart", True))
            self._minimized_row.set(self._config.get("general.start_minimized", True))
            if hasattr(self, "_auto_update_row"):
                self._auto_update_row.set(self._config.get("general.auto_update", True))
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
            if hasattr(self, "_role_row"):
                self._preview.set_role_visible(self._role_row.get())
        if hasattr(self, "_lang_menu"):
            self._lang_menu.set(
                self._code_to_lang_label(self._config.get("general.language", "auto"))
            )

    # Status

    def _start_breathe(self, dot: ctk.CTkLabel, base_hex: str):
        """Continuously breathe (fade in/out) a dot using its current base color."""
        import math

        def _hex_to_rgb(h: str):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        def _rgb_to_hex(r, g, b):
            return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

        br, bg_, bb = _hex_to_rgb(base_hex)
        DIM = 0.3
        PERIOD_MS = 2000
        STEP_MS = 40

        # Each call gets a unique token; old loops see a stale token and stop
        token = object()
        dot._breathe_token = token

        def _tick(t: int):
            if not dot.winfo_exists():
                return
            if getattr(dot, "_breathe_token", None) is not token:
                return
            alpha = (1 - math.cos(2 * math.pi * t / PERIOD_MS)) / 2
            brightness = DIM + (1 - DIM) * alpha
            color = _rgb_to_hex(br * brightness, bg_ * brightness, bb * brightness)
            dot.configure(text_color=color)
            dot.after(STEP_MS, lambda: _tick((t + STEP_MS) % PERIOD_MS))

        _tick(0)

    def set_discord_status(self, connected: bool):
        if not hasattr(self, "_discord_dot"):
            return
        color = GREEN if connected else RED
        self._discord_dot.configure(text_color=color)
        self._start_breathe(self._discord_dot, color)

    def set_lol_status(self, connected: bool):
        if not hasattr(self, "_lol_dot"):
            return
        color = GREEN if connected else RED
        self._lol_dot.configure(text_color=color)
        self._start_breathe(self._lol_dot, color)

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

    # Pause

    def _toggle_pause(self):
        if self._on_pause_toggle:
            self._on_pause_toggle()
        self._sync_pause_ui()

    def _sync_pause_ui(self):
        paused = self._is_paused_fn() if self._is_paused_fn else False
        if paused:
            self._status_dot.configure(text="⏸ RPC Paused", text_color=MUTED)
            self._pause_btn.configure(text="Resume RPC", fg_color=ACCENT, hover_color=ACCENT_DIM)
        else:
            self._status_dot.configure(text="● RPC Active", text_color=GREEN)
            self._pause_btn.configure(text="Pause RPC", fg_color=CARD, hover_color=BORDER2)

    def set_paused(self, paused: bool):
        """Called externally (e.g. from tray) to sync UI state."""
        self._sync_pause_ui()

    # Close

    def _close(self):
        self.withdraw()
        if self._on_close:
            self._on_close()
    
    # Show Welcome Popup
    def _show_welcome(self):
        from tkinter import messagebox

        msg = ( 
            "Welcome to LoLCustomRPC!\n\n"
            "IMPORTANT: For the application to detect your game correctly, "
            "you must always start LoLCustomRPC BEFORE opening League of Legends.\n\n"
            "If you open the app while the game is already running, it might will be overridden by League's official RPC.\n\n"
            "Note: Since the app is set to start automatically with Windows, you only need "
            "to open it manually this first time (unless you turn off auto-start in Settings)."
        )
        
        # Show popup
        messagebox.showinfo("Important Notice", msg, parent=self)
        
        # Save to config that we've shown the welcome message, so it doesn't show again
        self._config.set("general.shown_welcome", True)
        self._config.save()
