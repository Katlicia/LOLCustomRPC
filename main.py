"""
LoL RPC Custom - Entry point.

Startup behaviour:
  - python main.py              → window visible (dev mode / double-click exe)
  - python main.py --minimized  → tray only  (injected by Windows autostart registry)
"""

import os
import sys
import time
import logging
import threading

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.rpc_manager import RPCManager
from core.state_machine import StateMachine, State, DisplayOptions
from core.ddragon import DDragon
from i18n.translator import Translator
from services.config import ConfigManager
from services import autostart
from ui.api import API
from ui.window import WebWindow
from ui.tray import TrayIcon

load_dotenv()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID") or None

POLL_INTERVALS = {
    State.OFFLINE:      30.0,
    State.MAIN_MENU:    10.0,
    State.LOBBY:         8.0,
    State.MATCHMAKING:   5.0,
    State.CHAMP_SELECT:  3.0,
    State.IN_GAME:       4.0,
    State.POST_GAME:    10.0,
}


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# RPC loop (background thread)
# ---------------------------------------------------------------------------

def rpc_loop(
    sm: StateMachine,
    rpc: RPCManager,
    tray: TrayIcon,
    stop_event: threading.Event,
):
    logger = logging.getLogger("rpc_loop")
    current_state = State.OFFLINE
    last_health = 0.0

    while not stop_event.is_set():
        try:
            now = time.time()
            if now - last_health >= 30:
                if not rpc.connected:
                    logger.info("Discord disconnected, reconnecting...")
                    rpc.try_reconnect()
                last_health = now

            if not tray.is_paused:
                payload = sm.build_payload()
                current_state = payload.state_name if payload else State.OFFLINE
                rpc.update(payload)

            tray.set_connected(rpc.connected)

        except Exception as e:
            logger.exception(f"Loop error: {e}")

        stop_event.wait(timeout=POLL_INTERVALS.get(current_state, 10.0))

    rpc.disconnect()
    logger.info("RPC loop stopped.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    setup_logging()
    logger = logging.getLogger("main")

    if not CLIENT_ID:
        logger.error(
            "Discord client ID not set. "
            "Create a .env file with DISCORD_CLIENT_ID=your_id"
        )
        sys.exit(1)

    launched_by_autostart = "--minimized" in sys.argv

    # Config
    config = ConfigManager()
    autostart.sync(config.get("general.autostart", True))
    config.on_save(lambda: autostart.sync(config.get("general.autostart", True)))

    # Core
    ddragon    = DDragon()
    translator = Translator(locale=config.get("general.language", "auto"))
    sm = StateMachine(
        ddragon, translator,
        options=DisplayOptions(
            show_nick=config.get("display.show_nick", True),
            show_tag=config.get("display.show_tag", True),
            show_rank=config.get("display.show_rank", True),
        ),
    )

    rpc = RPCManager(CLIENT_ID)
    rpc.connect()
    config.on_save(lambda: sm.apply_config(config))

    logger.info(f"Starting — locale: {translator.active_locale}")

    stop_event = threading.Event()

    # PyWebView API + window
    api = API(config=config, state_machine=sm)
    web = WebWindow(api=api, on_closed=lambda: stop_event.set())

    # Tray
    def open_window():
        web.show()

    def quit_app():
        stop_event.set()
        web.destroy()

    tray = TrayIcon(on_open_settings=open_window, on_quit=quit_app)
    tray.start()

    # RPC loop
    rpc_thread = threading.Thread(
        target=rpc_loop,
        args=(sm, rpc, tray, stop_event),
        daemon=True,
    )
    rpc_thread.start()

    # Start webview — BLOCKS on main thread until window closes
    hide_on_start = launched_by_autostart and config.get("general.start_minimized", True)
    logger.info("Ready.")
    web.start(hidden=hide_on_start)

    # After window closes
    stop_event.set()
    tray.stop()
    logger.info("Bye.")


if __name__ == "__main__":
    main()