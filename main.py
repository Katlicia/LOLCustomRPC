"""
LoLCustomRPC - Entry point.

Startup behaviour:
  - python main.py              -> window visible (dev mode / double-click exe)
  - python main.py --minimized  -> tray only (injected by Windows autostart registry)
"""

import os
import sys
import time
import logging
import threading
import ctypes

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
from services.updater import check_async
from ui.tray import TrayIcon
from ui.settings_window import SettingsWindow

load_dotenv()

# _client_id.py is generated at build time (gitignored) and baked into the exe.
# Falls back to .env for local development.
try:
    from _client_id import CLIENT_ID  # type: ignore
except ImportError:
    CLIENT_ID = os.getenv("DISCORD_CLIENT_ID") or None
APP_VERSION = "1.0.0"

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


# RPC loop (background thread)
def rpc_loop(
    sm: StateMachine,
    rpc: RPCManager,
    tray: TrayIcon,
    stop_event: threading.Event,
    win_ref: list,
):
    logger = logging.getLogger("rpc_loop")
    current_state = State.OFFLINE
    last_health = 0.0
    last_lol_connected = False
    last_discord_connected = False

    while not stop_event.is_set():
        try:
            now = time.time()
            if now - last_health >= 30:
                if not rpc.connected:
                    logger.info("Discord not connected — attempting reconnect.")
                    rpc.try_reconnect()
                last_health = now

            payload = None
            if not tray.is_paused:
                payload = sm.build_payload()
                current_state = payload.state_name if payload else State.OFFLINE
                rpc.update(payload)

            lol_connected = payload is not None
            discord_connected = rpc.connected

            tray.set_connected(discord_connected)

            if win_ref:
                win = win_ref[0]
                if lol_connected != last_lol_connected:
                    status = lol_connected
                    win.after(0, lambda s=status: win.set_lol_status(s))
                    logger.info(f"LoL status: {'connected' if lol_connected else 'disconnected'}.")
                if discord_connected != last_discord_connected:
                    status = discord_connected
                    win.after(0, lambda s=status: win.set_discord_status(s))
                    logger.info(f"Discord status: {'connected' if discord_connected else 'disconnected'}.")

            last_lol_connected = lol_connected
            last_discord_connected = discord_connected

        except Exception as e:
            logger.exception(f"Loop error: {e}")

        stop_event.wait(timeout=POLL_INTERVALS.get(current_state, 10.0))

    rpc.disconnect()
    logger.info("RPC loop stopped.")


# Main
def main():
    # Mutex control
    mutex_name = "LoLCustomRPC_SingleInstance_Lock"

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)

    if ctypes.windll.kernel32.GetLastError() == 183:
            print("Another instance is already running. Exiting.")
            sys.exit(0)

    setup_logging()
    logger = logging.getLogger("main")

    if not CLIENT_ID:
        logger.error(
            "Discord client ID not set. "
            "Create a .env file with DISCORD_CLIENT_ID=your_id"
        )
        sys.exit(1)

    # --minimized is injected by the registry autostart entry
    # When the user double-clicks the exe directly, this flag is absent
    launched_by_autostart = "--minimized" in sys.argv

    # Config
    config = ConfigManager()
    autostart.sync(config.get("general.autostart", True))
    config.on_save(lambda: autostart.sync(config.get("general.autostart", True)))

    # Core components
    ddragon    = DDragon()
    translator = Translator(locale=config.get("general.language", "auto"))
    sm = StateMachine(
        ddragon, translator,
        options=DisplayOptions(
            show_nick=config.get("display.show_nick", True),
            show_tag=config.get("display.show_tag",  True),
            show_rank=config.get("display.show_rank", True),
            show_level=config.get("display.show_level", True),
            show_kda=config.get("display.show_kda", True),
            show_role=config.get("display.show_role", True),
            logo=config.get("display.logo", "lol_logo"),
        ),
    )

    rpc = RPCManager(CLIENT_ID)
    rpc.connect()
    config.on_save(lambda: sm.apply_config(config))

    logger.info(f"Starting — locale: {translator.active_locale}")

    stop_event = threading.Event()
    win_ref: list[SettingsWindow] = []

    def open_settings():
        if win_ref:
            def _show():
                w = win_ref[0]
                w.deiconify()
                w.lift()
                w.focus_force()
            win_ref[0].after(0, _show)

    def quit_app():
        stop_event.set()
        if win_ref:
            win_ref[0].after(0, win_ref[0].destroy)

    def on_pause_changed(paused: bool):
        if win_ref:
            win_ref[0].after(0, win_ref[0].set_paused, paused)

    # Tray
    tray = TrayIcon(on_open_settings=open_settings, on_quit=quit_app, on_pause_changed=on_pause_changed)
    tray.start()

    # RPC loop in background thread
    rpc_thread = threading.Thread(
        target=rpc_loop,
        args=(sm, rpc, tray, stop_event, win_ref),
        daemon=True,
    )
    rpc_thread.start()

    # Settings window — Tkinter must live on the main thread
    win = SettingsWindow(
        config=config,
        translator=translator,
        app_version=APP_VERSION,
        on_pause_toggle=tray.toggle_pause,
        is_paused_fn=lambda: tray.is_paused,
    )
    win_ref.append(win)

    # Background update check — notifies via win.notify_update on the main thread
    check_async(
        APP_VERSION,
        on_update_found=lambda info: win.notify_update(info),
    )

    # Show window:
    #   - Always show when launched manually (double-click exe or python main.py)
    #   - Hide to tray only when launched by autostart AND start_minimized is on
    hide_on_start = launched_by_autostart and config.get("general.start_minimized", True)
    if hide_on_start:
        win.withdraw()
    else:
        win.deiconify()

    logger.info("Ready.")

    try:
        win.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        tray.stop()
        logger.info("Bye.")


if __name__ == "__main__":
    main()