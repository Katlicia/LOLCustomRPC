"""
System Tray integration using pystray + Pillow.

Menu:
  LoLCustomRPC (title, disabled)
  Open Settings
  Pause RPC  /  Resume RPC  (toggle)
  Quit

Double-clicking the icon opens Settings.
"""

import threading
import logging
from typing import Callable, Optional


from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

logger = logging.getLogger(__name__)


import os as _os
_ASSETS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "assets")
_TRAY_PNG = _os.path.join(_ASSETS, "winicon.png")


def _load_tray_icon() -> Image.Image:
    if _os.path.exists(_TRAY_PNG):
        return Image.open(_TRAY_PNG).convert("RGBA")
    # Fallback: generated placeholder
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill="#5865f2")
    return img


class TrayIcon:
    """
    Manages the system tray icon lifecycle.
    Runs pystray in a background thread so the main thread stays free
    for the Tkinter event loop.
    """

    def __init__(
        self,
        on_open_settings: Callable,
        on_quit: Callable,
        on_pause_changed: Optional[Callable] = None,
    ):
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit
        self._on_pause_changed = on_pause_changed
        self._paused = False
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    # Lifecycle
    def start(self):
        """Start the tray icon in a daemon thread."""
        self._icon = pystray.Icon(
            name="lol-rpc-custom",
            icon=_load_tray_icon(),
            title="LoLCustomRPC",
            menu=self._build_menu(),
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started.")

    def stop(self):
        if self._icon:
            self._icon.stop()

    # Menu
    def _build_menu(self) -> Menu:
        return Menu(
            item("LoLCustomRPC", lambda: None, enabled=False),
            Menu.SEPARATOR,
            item("Open Settings", lambda: self._open_settings(), default=True),
            Menu.SEPARATOR,
            item(
                "Pause RPC",
                lambda: self._toggle_pause(),
                checked=lambda i: self._paused,
            ),
            Menu.SEPARATOR,
            item("Quit", lambda: self._quit()),
        )

    def _refresh_menu(self):
        """Force pystray to re-render the menu (e.g. after pause toggle)."""
        if self._icon:
            self._icon.menu = self._build_menu()
            self._icon.update_menu()

    # Actions
    def _open_settings(self):
        # pystray runs on a non-main thread; use after() to stay thread-safe
        self._on_open_settings()

    def _toggle_pause(self):
        self._paused = not self._paused
        img = _load_tray_icon()
        if self._paused:
            r, g, b, a = img.split()
            a = a.point(lambda x: int(x * 0.4))
            img = Image.merge("RGBA", (r, g, b, a))
        self._icon.icon = img
        self._refresh_menu()
        if self._on_pause_changed:
            self._on_pause_changed(self._paused)
        logger.info(f"RPC {'paused' if self._paused else 'resumed'}.")

    def toggle_pause(self):
        """Public method — called from settings window."""
        self._toggle_pause()

    def _quit(self):
        self.stop()
        self._on_quit()

    # Public state helpers
    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_connected(self, connected: bool):
        """Dim icon when disconnected from Discord."""
        if self._icon and not self._paused:
            img = _load_tray_icon()
            if not connected:
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * 0.4))
                img = Image.merge("RGBA", (r, g, b, a))
            self._icon.icon = img
