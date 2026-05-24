"""
Auto-updater for LoLCustomRPC.

Flow:
  1. check_for_update()  -> returns UpdateInfo or None
  2. download_and_install(info) -> downloads new .exe, replaces current exe via helper script, restarts
"""

import ctypes
import logging
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/repos/Katlicia/LOLCustomRPC/releases/latest"
TIMEOUT = 10


@dataclass
class UpdateInfo:
    version: str        # e.g. "1.2.0"
    download_url: str   # direct .exe asset URL
    release_url: str    # HTML page URL for "View on GitHub"
    notes: str          # release body (trimmed)


def _parse_version(v: str) -> tuple:
    """'v1.2.0' or '1.2.0' -> (1, 2, 0)"""
    v = v.lstrip("v").strip()
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def check_for_update(current_version: str) -> Optional[UpdateInfo]:
    """
    Query GitHub Releases API. Returns UpdateInfo if a newer version exists,
    None if up-to-date or on any network/parse error.
    """
    try:
        resp = requests.get(GITHUB_API, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Update check failed: {e}")
        return None

    latest_tag = data.get("tag_name", "")
    if not latest_tag:
        return None

    if _parse_version(latest_tag) <= _parse_version(current_version):
        return None

    # Find the .exe asset
    exe_url = None
    for asset in data.get("assets", []):
        name: str = asset.get("name", "")
        if name.lower().endswith(".exe"):
            exe_url = asset.get("browser_download_url")
            break

    if not exe_url:
        logger.warning("New release found but no .exe asset attached.")
        return None

    notes = (data.get("body") or "").strip()
    if len(notes) > 300:
        notes = notes[:297] + "..."

    return UpdateInfo(
        version=latest_tag.lstrip("v"),
        download_url=exe_url,
        release_url=data.get("html_url", ""),
        notes=notes,
    )


def download_and_install(
    info: UpdateInfo,
    on_progress: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
):
    """
    Download the new .exe and replace the running executable.
    Spawns a detached helper script that waits for this process to exit,
    overwrites the exe, then relaunches.

    on_progress(percent: int) — called with 0-100 during download
    on_error(message: str)    — called if anything goes wrong
    """
    current_exe = sys.executable if getattr(sys, "frozen", False) else None
    if not current_exe:
        if on_error:
            on_error("Auto-install is only supported when running as a packaged .exe.")
        return

    def _run():
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="lolrpc_new_")
            os.close(tmp_fd)

            # Download with streaming
            resp = requests.get(info.download_url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and on_progress:
                            on_progress(int(downloaded * 100 / total))
            if on_progress:
                on_progress(100)

            # Get file path
            exe_dir = os.path.dirname(current_exe)

            # Write a tiny batch script to update
            pid = os.getpid()
            script = (
                f"@echo off\n"
                f"set _MEIPASS2=\n"
                f"set _MEIPASS=\n"
                f"set PYMEIPASS=\n"
                f"cd /d \"{exe_dir}\"\n"
                f":retry\n"
                f"timeout /t 1 /nobreak >NUL\n"
                f"copy /y \"{tmp_path}\" \"{current_exe}\" >NUL\n"
                f"if errorlevel 1 goto retry\n"
                f"del \"{tmp_path}\" >NUL\n"
                f"start \"\" \"{current_exe}\"\n"
                f"del \"%~f0\"\n"
            )
            bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="lolrpc_script_")
            with os.fdopen(bat_fd, "w") as f:
                f.write(script)

            os.environ.pop("_MEIPASS2", None)
            os.environ.pop("PYMEIPASS", None)

            ctypes.windll.shell32.ShellExecuteW(
                None, 
                "open", 
                "cmd.exe", 
                f'/c "{bat_path}"', 
                exe_dir, 
                0
            )
           
            os._exit(0)

        except Exception as e:
            logger.error(f"Update install failed: {e}")
            if on_error:
                on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


def check_async(
    current_version: str,
    on_update_found: Callable[[UpdateInfo], None],
):
    """Run check_for_update in a background thread; call on_update_found if newer."""
    def _run():
        info = check_for_update(current_version)
        if info:
            on_update_found(info)

    threading.Thread(target=_run, daemon=True).start()
