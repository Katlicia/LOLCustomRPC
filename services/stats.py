"""
Anonymous usage stats.

- On first run, generates a random UUIDv4 and stores it locally
  (%APPDATA%/LoLRPCCustom/device_id.txt). This id identifies a device, not a
  person — no personal or gameplay data is ever sent.
- Sends a one-time "install" ping and periodic "heartbeat" pings to the
  stats backend so the app can show live user count + total installs.
- Every network call is best-effort: failures are swallowed, never raised,
  and never block or slow down the RPC loop.

Naming note: this module's "device_id" is unrelated to the Discord
application CLIENT_ID used for Rich Presence (_client_id.py) — the JSON
field sent to the stats API is called "client_id" for API simplicity, but
locally we call it device_id to avoid confusion with the Discord one.
"""

import logging
import os
import uuid
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Cloudflare Worker URL — see cf-worker/README.md for deploy instructions.
STATS_API_BASE = "https://lolcustomrpc-stats.katlicia.workers.dev"

TIMEOUT = 5
HEARTBEAT_INTERVAL = 5 * 60  # seconds


def _default_stats_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "LoLRPCCustom")


def _device_id_path() -> str:
    return os.path.join(_default_stats_dir(), "device_id.txt")


def get_or_create_device_id() -> str:
    """
    Returns this device's persistent anonymous id, generating and saving a
    new one on first run.
    """
    path = _device_id_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read().strip()
            if existing:
                return existing
    except OSError as e:
        logger.debug(f"Could not read device_id file: {e}")

    new_id = str(uuid.uuid4())
    try:
        os.makedirs(_default_stats_dir(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_id)
    except OSError as e:
        logger.debug(f"Could not persist device_id: {e}")
    return new_id


def send_install(device_id: str, version: str) -> None:
    """Fire-and-forget: report a fresh installation. Safe to call every launch."""
    try:
        requests.post(
            f"{STATS_API_BASE}/install",
            json={"client_id": device_id, "version": version},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        logger.debug(f"Install ping failed (ignored): {e}")


def send_heartbeat(device_id: str, version: str) -> None:
    """Fire-and-forget: report that this client is currently running."""
    try:
        requests.post(
            f"{STATS_API_BASE}/heartbeat",
            json={"client_id": device_id, "version": version},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        logger.debug(f"Heartbeat ping failed (ignored): {e}")


def fetch_stats() -> Optional[dict]:
    """Returns {"online": int, "total_installs": int} or None on failure."""
    try:
        resp = requests.get(f"{STATS_API_BASE}/stats", timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug(f"Fetching stats failed (ignored): {e}")
        return None
