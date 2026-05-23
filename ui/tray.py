"""
System Tray integration using pystray + Pillow.

Menu:
  LoL RPC Custom (title, disabled)
  ─────────────
  Open Settings
  ─────────────
  Pause RPC  /  Resume RPC  (toggle)
  ─────────────
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


def _make_icon_image(color: str = "#5865f2", size: int = 64) -> Image.Image:
    """
    Generate a simple tinted circular icon.
    In production this would load a proper .ico asset from assets/.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer circle
    draw.ellipse([2, 2, size - 2, size - 2], fill=color)
    # Inner "L" shape (LoL reference)
    m = size // 5
    draw.rectangle([m, m, m * 2, size - m], fill="white")
    draw.rectangle([m, size - m * 2, size - m, size - m], fill="white")
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
    ):
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit
        self._paused = False
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the tray icon in a daemon thread."""
        self._icon = pystray.Icon(
            name="lol-rpc-custom",
            icon=_make_icon_image(),
            title="LoL RPC Custom",
            menu=self._build_menu(),
        )
        # Double-click opens settings
        self._icon.default_action = lambda icon, item: self._open_settings()

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started.")

    def stop(self):
        if self._icon:
            self._icon.stop()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> Menu:
        return Menu(
            item("LoL RPC Custom", lambda: None, enabled=False),
            Menu.SEPARATOR,
            item("Open Settings", lambda: self._open_settings()),
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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_settings(self):
        # pystray runs on a non-main thread; use after() to stay thread-safe
        self._on_open_settings()

    def _toggle_pause(self):
        self._paused = not self._paused
        self._icon.icon = _make_icon_image(
            color="#72767d" if self._paused else "#5865f2"
        )
        self._refresh_menu()
        logger.info(f"RPC {'paused' if self._paused else 'resumed'}.")

    def _quit(self):
        self.stop()
        self._on_quit()

    # ------------------------------------------------------------------
    # Public state helpers
    # ------------------------------------------------------------------

    @property
    def is_paused(self) -> bool:
        return self._paused

    def set_connected(self, connected: bool):
        """Change icon tint to reflect Discord connection status."""
        if self._icon and not self._paused:
            self._icon.icon = _make_icon_image(
                color="#5865f2" if connected else "#ed4245"
            )
