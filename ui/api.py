"""
PyWebView JS API.

Every public method here is callable from JavaScript as:
    window.pywebview.api.method_name(args)

All methods must be synchronous (pywebview runs them on a thread pool).
Return values are automatically JSON-serialised by pywebview.

Log streaming:
    The RPC loop calls api.push_log(msg) which queues messages.
    The JS side polls via api.get_logs() every 500ms.
"""

import logging
import queue
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class API:
    """
    Exposed to JavaScript via window.pywebview.api.*
    Created once in main.py and passed to webview.create_window().
    """

    def __init__(self, config, state_machine):
        self._config = config
        self._sm = state_machine
        self._log_q: queue.Queue = queue.Queue(maxsize=1000)
        self._window = None          # set after window is created
        self._lock = threading.Lock()

        # Attach a logging handler so all logger.* calls feed the log queue
        handler = _QueueHandler(self._log_q)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)

    def set_window(self, window):
        """Called by window.py after webview.create_window() returns."""
        self._window = window

    # ------------------------------------------------------------------ #
    # Config — read                                                        #
    # ------------------------------------------------------------------ #

    def get_config(self) -> dict:
        """Return the full config as a flat-ish dict for the settings UI."""
        return {
            "show_nick":      self._config.get("display.show_nick", True),
            "show_tag":       self._config.get("display.show_tag", True),
            "show_rank":      self._config.get("display.show_rank", True),
            "logo":           self._config.get("display.logo", "lol_legacy_logo"),
            "autostart":      self._config.get("general.autostart", True),
            "start_minimized":self._config.get("general.start_minimized", True),
            "language":       self._config.get("general.language", "auto"),
        }

    # ------------------------------------------------------------------ #
    # Config — write                                                       #
    # ------------------------------------------------------------------ #

    def save_config(self, data: dict) -> dict:
        """
        Persist display + general settings from the JS settings panel.
        Returns {"ok": True} or {"ok": False, "error": "..."}.
        """
        try:
            mapping = {
                "show_nick":       "display.show_nick",
                "show_tag":        "display.show_tag",
                "show_rank":       "display.show_rank",
                "logo":            "display.logo",
                "autostart":       "general.autostart",
                "start_minimized": "general.start_minimized",
                "language":        "general.language",
            }
            for js_key, config_key in mapping.items():
                if js_key in data:
                    self._config.set(config_key, data[js_key])
            self._config.save()   # fires hot-reload callbacks (sm.apply_config)
            logger.info("Config saved.")
            return {"ok": True}
        except Exception as e:
            logger.error(f"save_config failed: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """
        Current RPC + LoL connection status.
        Polled by JS every few seconds to update the status indicator.
        """
        from core.state_machine import State
        try:
            state = self._sm.detect_state()
            return {
                "lol_open":    state != State.OFFLINE,
                "state":       state.value,
                "state_label": _STATE_LABELS.get(state.value, state.value),
            }
        except Exception:
            return {"lol_open": False, "state": "offline", "state_label": "Offline"}

    # ------------------------------------------------------------------ #
    # Log streaming                                                        #
    # ------------------------------------------------------------------ #

    def get_logs(self) -> list:
        """
        Drain up to 50 log lines from the queue.
        Called by JS on a 500ms interval.
        """
        lines = []
        try:
            for _ in range(50):
                lines.append(self._log_q.get_nowait())
        except queue.Empty:
            pass
        return lines

    def push_log(self, msg: str):
        """Called internally (not from JS) to inject a message."""
        try:
            self._log_q.put_nowait(msg)
        except queue.Full:
            pass

    # ------------------------------------------------------------------ #
    # Window control (called from JS)                                     #
    # ------------------------------------------------------------------ #

    def minimize_to_tray(self):
        """Hide the window (go to tray) when user clicks the close button."""
        if self._window:
            self._window.hide()
        return {"ok": True}


# ── Helpers ────────────────────────────────────────────────────────────────

_STATE_LABELS = {
    "offline":      "LoL is closed",
    "main_menu":    "Main menu",
    "lobby":        "In lobby",
    "matchmaking":  "In queue",
    "champ_select": "Champion select",
    "in_game":      "In game",
    "post_game":    "Post game",
}


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord):
        try:
            self._q.put_nowait(self.format(record))
        except queue.Full:
            pass