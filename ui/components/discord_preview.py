"""
Discord RPC Preview Widget — pixel-accurate mock of the Discord activity card.
All images are loaded from assets/ (packaged with the app, no network calls).

  assets/default_logos/lol_logo.png
  assets/default_logos/lol_legacy_logo.png
  assets/preview/champion.png   — shown in Champion Select
  assets/preview/skin.png       — shown In Game
  assets/preview/avatar.png     — small icon overlay on all states
"""

import os
from typing import Optional, TYPE_CHECKING

import customtkinter as ctk
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from i18n.translator import Translator

ROOT_DIR      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGOS_DIR     = os.path.join(ROOT_DIR, "assets", "default_logos")
PREVIEW_DIR   = os.path.join(ROOT_DIR, "assets", "preview")

D_BG      = "#1e1f22"
D_SURFACE = "#232428"
D_TEXT    = "#f2f3f5"
D_MUTED   = "#949ba4"
D_BORDER  = "#3d4047"

STATE_DUMMIES = {
    "In Game": {
        "details":   "Gwen - Solo/Duo",
        "kda":       "5/2/3",
        "role":      "Top",
        "elapsed":   "23:47",
        "large_key": "skin",
        "small_key": "avatar",
    },
    "Champion Select": {
        "details":   "Picking champion - Solo/Duo",
        "state":     "Summoner#EUW | Gold IV",
        "elapsed":   None,
        "large_key": "champion",
        "small_key": "avatar",
    },
    "In Lobby": {
        "details":   "In lobby - Solo/Duo",
        "state":     "Summoner#EUW | Gold IV",
        "elapsed":   None,
        "large_key": "logo",
        "small_key": "avatar",
    },
    "Main Menu": {
        "details":   "In main menu",
        "state":     "Summoner#EUW | Gold IV | Lv.150",
        "elapsed":   None,
        "large_key": "logo",
        "small_key": "avatar",
    },
}


# Image helpers

def _make_placeholder(w: int, h: int, color: str = D_SURFACE, text: str = "") -> Image.Image:
    img = Image.new("RGBA", (w, h), color)
    if text:
        ImageDraw.Draw(img).text((w // 2, h // 2), text, fill="#555", anchor="mm")
    return img


def _load_asset(path: str, size: tuple) -> Optional[Image.Image]:
    if not os.path.exists(path):
        return None
    try:
        return Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
    except Exception:
        return None


def _ctk(raw: Image.Image, size: tuple) -> ctk.CTkImage:
    return ctk.CTkImage(light_image=raw, dark_image=raw, size=size)


# Widget

class DiscordPreview(ctk.CTkFrame):
    """
    Pixel-accurate Discord activity card mock.

    Public API:
        set_state(name)
        set_logo(key)           — "lol_logo" | "lol_legacy_logo"
        set_nick_visible(bool)
        set_tag_visible(bool)
        set_rank_visible(bool)
        set_level_visible(bool)
        set_kda_visible(bool)
    """

    LARGE_SIZE = (64, 64)
    SMALL_SIZE = (20, 20)

    def __init__(self, master, translator: Optional["Translator"] = None, **kwargs):
        super().__init__(
            master,
            fg_color=D_SURFACE,
            corner_radius=12,
            border_width=1,
            border_color=D_BORDER,
            **kwargs,
        )
        self._t          = translator
        self._logo_key   = "lol_logo"
        self._state_key  = "In Game"
        self._show_nick  = True
        self._show_tag   = True
        self._show_rank  = True
        self._show_level = True
        self._show_kda   = True
        self._show_role  = True

        # CTkImage refs — must be kept alive to prevent GC
        self._large_ctk: Optional[ctk.CTkImage] = None
        self._small_ctk: Optional[ctk.CTkImage] = None

        # Preload assets once at init
        self._assets: dict[str, Optional[Image.Image]] = {
            "lol_logo":        _load_asset(os.path.join(LOGOS_DIR, "lol_logo.png"),        self.LARGE_SIZE),
            "lol_legacy_logo": _load_asset(os.path.join(LOGOS_DIR, "lol_legacy_logo.png"), self.LARGE_SIZE),
            "champion":        _load_asset(os.path.join(PREVIEW_DIR, "champion.png"),       self.LARGE_SIZE),
            "skin":            _load_asset(os.path.join(PREVIEW_DIR, "skin.png"),           self.LARGE_SIZE),
            "avatar":          _load_asset(os.path.join(PREVIEW_DIR, "avatar.png"),         self.SMALL_SIZE),
        }

        self._build()

    # Layout

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text="PLAYING A GAME",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=D_MUTED, anchor="w",
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 10), sticky="w")

        # Image container: large (64×64) + small overlay (20×20) bottom-right
        img_wrap = ctk.CTkFrame(self, fg_color="transparent", width=78, height=72)
        img_wrap.grid(row=1, column=0, padx=(16, 8), pady=(0, 14), sticky="nw")
        img_wrap.grid_propagate(False)

        self._large_frame = ctk.CTkFrame(
            img_wrap, width=64, height=64, fg_color=D_BG, corner_radius=8,
        )
        self._large_frame.place(x=0, y=0)
        self._large_frame.grid_propagate(False)

        self._large_label = ctk.CTkLabel(self._large_frame, text="", image=None)
        self._large_label.place(relx=0.5, rely=0.5, anchor="center")

        self._small_label = ctk.CTkLabel(img_wrap, text="", image=None, fg_color="transparent")
        self._small_label.place(x=44, y=44)

        # Text block
        tf = ctk.CTkFrame(self, fg_color="transparent")
        tf.grid(row=1, column=1, padx=(0, 16), pady=(0, 14), sticky="nw")

        ctk.CTkLabel(
            tf, text="League of Legends",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=D_TEXT, anchor="w", wraplength=165, justify="left",
        ).pack(anchor="w", pady=(0, 2))

        self._details_label = ctk.CTkLabel(
            tf, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=D_TEXT, anchor="w", wraplength=165, justify="left",
        )
        self._details_label.pack(anchor="w")

        self._state_label = ctk.CTkLabel(
            tf, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=D_TEXT, anchor="w", wraplength=165, justify="left",
        )
        self._state_label.pack(anchor="w")

        self._elapsed_label = ctk.CTkLabel(
            tf, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=D_MUTED, anchor="w",
        )
        self._elapsed_label.pack(anchor="w", pady=(2, 0))

        self._refresh()

    # Public setters

    def set_state(self, name: str):
        self._state_key = name
        self._refresh()

    def set_logo(self, key: str):
        self._logo_key = key
        self._refresh()

    def set_nick_visible(self, v: bool):
        self._show_nick = v
        self._refresh()

    def set_tag_visible(self, v: bool):
        self._show_tag = v
        self._refresh()

    def set_rank_visible(self, v: bool):
        self._show_rank = v
        self._refresh()

    def set_level_visible(self, v: bool):
        self._show_level = v
        self._refresh()

    def set_kda_visible(self, v: bool):
        self._show_kda = v
        self._refresh()

    def set_role_visible(self, v: bool):
        self._show_role = v
        self._refresh()

    def set_translator(self, t: "Translator"):
        self._t = t
        self._refresh()

    # Refresh

    def _t_(self, key: str, **kw) -> str:
        if self._t:
            return self._t.t(key, **kw)
        return key

    def _refresh(self):
        dummy = STATE_DUMMIES.get(self._state_key, STATE_DUMMIES["In Game"])

        nick  = "Summoner#EUW" if self._show_tag else "Summoner"
        rank  = "Gold IV"
        level = self._t_("level_format", level=150)

        # State text
        if self._state_key == "In Game":
            kda  = dummy.get("kda", "")
            role = self._t_(f"role_{dummy.get('role', 'top').lower()}") if self._show_role else ""
            if self._show_kda and kda:
                state_text = self._t_("kda_with_role", k=5, d=2, a=3, role=role) if role else self._t_("kda_format", k=5, d=2, a=3)
            else:
                state_text = role or ""
            details_text = f"Gwen - {self._t_('queue_solo_duo')}"
        elif self._state_key == "Main Menu":
            parts = []
            if self._show_nick:
                parts.append(nick)
            if self._show_rank:
                parts.append(rank)
            if self._show_level:
                parts.append(level)
            state_text = " | ".join(parts)
            details_text = self._t_("in_main_menu")
        elif self._state_key == "Champion Select":
            parts = []
            if self._show_nick:
                parts.append(nick)
            if self._show_rank:
                parts.append(rank)
            state_text = " | ".join(parts)
            details_text = f"{self._t_('picking_champion')} - {self._t_('queue_solo_duo')}"
        else:  # In Lobby
            parts = []
            if self._show_nick:
                parts.append(nick)
            if self._show_rank:
                parts.append(rank)
            state_text = " | ".join(parts)
            details_text = f"{self._t_('in_lobby', queue=self._t_('queue_solo_duo'))}"

        self._details_label.configure(text=details_text)
        self._state_label.configure(text=state_text)

        elapsed = dummy.get("elapsed")
        if elapsed:
            self._elapsed_label.configure(text=f"{elapsed} elapsed")
            self._elapsed_label.pack(anchor="w", pady=(2, 0))
        else:
            self._elapsed_label.configure(text="")
            self._elapsed_label.pack_forget()

        self._update_large(dummy.get("large_key", "logo"))
        self._update_small(dummy.get("small_key"))

    # Image rendering

    def _update_large(self, key: str):
        if key == "logo":
            raw = self._assets.get(self._logo_key)
        else:
            raw = self._assets.get(key)

        if raw is None:
            raw = _make_placeholder(*self.LARGE_SIZE, D_BG, "?")

        self._large_ctk = _ctk(raw, self.LARGE_SIZE)
        self._large_label.configure(image=self._large_ctk, text="")

    def _update_small(self, key: Optional[str]):
        if not key:
            self._small_label.configure(image=None, text="")
            return

        raw = self._assets.get(key)
        if raw is None:
            raw = _make_placeholder(*self.SMALL_SIZE, D_BG)

        self._small_ctk = _ctk(raw, self.SMALL_SIZE)
        self._small_label.configure(image=self._small_ctk, text="")
