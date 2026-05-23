"""
Windows autostart management via the registry.

Key: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Value: LoLRPCCustom = "C:\\path\\to\\lol-rpc-custom.exe --minimized"

--minimized flag tells main.py to skip showing the window on startup.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "LoLRPCCustom"


def _get_exe_path() -> str:
    """Return the path to use in the registry value."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller .exe
        return f'"{sys.executable}" --minimized'
    else:
        # Running as a Python script (dev mode)
        main_script = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "main.py")
        )
        return f'"{sys.executable}" "{main_script}" --minimized'


def enable() -> bool:
    """Add the app to Windows startup. Returns True on success."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, _get_exe_path())
        logger.info("Autostart enabled.")
        return True
    except Exception as e:
        logger.error(f"Could not enable autostart: {e}")
        return False


def disable() -> bool:
    """Remove the app from Windows startup. Returns True on success."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, REG_VALUE_NAME)
        logger.info("Autostart disabled.")
        return True
    except FileNotFoundError:
        return True  # Already absent - that's fine
    except Exception as e:
        logger.error(f"Could not disable autostart: {e}")
        return False


def is_enabled() -> bool:
    """Check whether autostart is currently registered."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, REG_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def sync(enabled: bool):
    """Enable or disable based on a boolean — convenient for config callbacks."""
    if enabled:
        enable()
    else:
        disable()
