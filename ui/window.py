"""
PyWebView window manager.
Injects ASSET_BASE into HTML so the frontend can reference local asset files
via the asset:// protocol (supported natively by pywebview).
"""

import os
import re
import logging
from typing import Callable, Optional

import webview
from ui.api import API

logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT_DIR, "ui", "index.html")


class WebWindow:
    def __init__(self, api: API, on_closed: Optional[Callable] = None):
        self._api      = api
        self._on_closed = on_closed
        self._window: Optional[webview.Window] = None

    def start(self, hidden: bool = False):
        """Blocks on main thread until the window is closed."""
        html = _load_html_with_asset_base(ROOT_DIR)

        self._window = webview.create_window(
            title="LoL RPC Custom",
            html=html,
            js_api=self._api,
            width=960,
            height=660,
            min_size=(820, 560),
            resizable=True,
            background_color="#0f1117",
        )
        self._api.set_window(self._window)

        if hidden:
            self._window.events.loaded += lambda: self._window.hide()

        webview.start(debug=False)

        if self._on_closed:
            self._on_closed()

    def show(self):
        if self._window:
            self._window.show()

    def hide(self):
        if self._window:
            self._window.hide()

    def destroy(self):
        if self._window:
            self._window.destroy()


def _load_html_with_asset_base(root: str) -> str:
    if not os.path.exists(HTML_PATH):
        return "<html><body style='background:#0f1117;color:#fff'>index.html not found</body></html>"

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject ASSET_BASE as a JS global so the frontend can build asset:// URLs
    # asset:// maps to the filesystem root on the machine running pywebview
    escaped = root.replace("\\", "/")
    inject = f"<script>window.ASSET_BASE = '{escaped}';</script>"
    html = html.replace("</head>", inject + "\n</head>", 1)
    return html