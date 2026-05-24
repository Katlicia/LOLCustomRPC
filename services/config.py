"""
ConfigManager - persistent user settings.

Design:
- Config lives at %APPDATA%/LoLRPCCustom/config.json (Windows standard)
- On first launch, default config is written to disk
- config.get(key) / config.set(key, value) use dot-notation: "display.show_nick"
- config.save() does an atomic write (temp file + rename) so no corrupt state
- On save, registered callbacks are fired so StateMachine can hot-reload options
  without any restart.

Hot-reload flow:
  GUI toggle changed -> preview updates (no write)
  User clicks Save   -> config.set(key, val) for each change -> config.save()
                     -> on_save callbacks fire -> StateMachine.options updated
  User clicks Cancel -> GUI reverts to config values, nothing written
"""

import json
import logging
import os
import tempfile
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# Default configuration

DEFAULTS: Dict[str, Any] = {
    "general": {
        "language": "auto",       # "auto" = follow LoL client locale
        "autostart": True,        # start with Windows
        "start_minimized": True,  # go straight to tray on launch
    },
    "display": {
        "show_nick": True,
        "show_tag": True,         # only meaningful when show_nick=True
        "show_rank": True,
        "show_level": True,
        "show_kda": True,
        "show_role": True,
        "logo": "lol_logo",  # "lol_logo" or "lol_legacy_logo"
    },
}

# Bump this when the schema changes so we can migrate old configs.
CONFIG_VERSION = 1


# Path helpers

def _default_config_dir() -> str:
    """Returns %APPDATA%/LoLRPCCustom on Windows."""
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "LoLRPCCustom")


def _default_config_path() -> str:
    return os.path.join(_default_config_dir(), "config.json")


# ConfigManager

class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        self._path = config_path or _default_config_path()
        self._data: Dict[str, Any] = {}
        self._save_callbacks: list[Callable] = []
        self.load()

    # Load / Save

    def load(self) -> bool:
        """
        Load config from disk. Missing keys are filled with defaults.
        Returns True on success (even if file didn't exist yet).
        """
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data = self._merge_with_defaults(saved)
                logger.info(f"Config loaded from {self._path}")
                return True
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not read config ({e}), using defaults.")

        # File missing or unreadable - start from defaults
        self._data = self._deep_copy(DEFAULTS)
        self._data["_version"] = CONFIG_VERSION
        self.save()  # write defaults to disk for next launch
        logger.info(f"Default config written to {self._path}")
        return True

    def save(self) -> bool:
        """
        Atomic write: write to a temp file then rename over the target.
        Fires all registered on_save callbacks after a successful write.
        """
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            dir_ = os.path.dirname(self._path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._path)  # atomic on same filesystem
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.debug("Config saved.")
            self._fire_callbacks()
            return True
        except OSError as e:
            logger.error(f"Could not save config: {e}")
            return False

    # Get / Set (dot-notation)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value by dot-notation key, e.g. config.get("display.show_nick").
        Returns `default` if the key doesn't exist.
        """
        parts = key.split(".")
        node = self._data
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        """
        Set a value by dot-notation key.
        Does NOT auto-save - caller decides when to call save().
        """
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Return a whole top-level section as a dict copy."""
        return dict(self._data.get(section, {}))

    # Hot-reload callbacks

    def on_save(self, callback: Callable) -> None:
        """
        Register a function to be called after every successful save().
        Used by StateMachine / GUI to react to config changes without restart.

        Example:
            config.on_save(lambda: sm.apply_config(config))
        """
        self._save_callbacks.append(callback)

    def _fire_callbacks(self) -> None:
        for cb in self._save_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning(f"on_save callback error: {e}")

    # Helpers

    @staticmethod
    def _deep_copy(d: dict) -> dict:
        return json.loads(json.dumps(d))

    def _merge_with_defaults(self, saved: dict) -> dict:
        """
        Deep-merge saved config with defaults so new keys added in future
        versions are automatically present without wiping user settings.
        """
        result = self._deep_copy(DEFAULTS)
        result["_version"] = saved.get("_version", CONFIG_VERSION)
        for section, values in saved.items():
            if section.startswith("_"):
                continue
            if section in result and isinstance(result[section], dict) and isinstance(values, dict):
                result[section].update(values)
            else:
                result[section] = values
        return result
