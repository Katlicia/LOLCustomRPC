"""
LCU (League Client Update) API client.
- finds the LeagueClient.exe process using psutil and derives the lockfile path
- reads port and password from the lockfile
- performs HTTPS Basic Auth GET requests to the API
"""

import os
import base64
import json
import logging
from typing import Optional, Tuple, Any

import psutil
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


# Fallback paths (if psutil fails)
FALLBACK_PATHS = [
    r"C:\Riot Games\League of Legends\lockfile",
    r"D:\Riot Games\League of Legends\lockfile",
    r"C:\Program Files\Riot Games\League of Legends\lockfile",
    r"C:\Program Files (x86)\Riot Games\League of Legends\lockfile",
]


class LCUClient:
    """Lightweight HTTP client for the League Client API."""

    def __init__(self):
        self.port: Optional[str] = None
        self.password: Optional[str] = None
        self.lockfile_path: Optional[str] = None
        self._auth_header: Optional[str] = None

    # Find lockfile

    def find_lockfile(self) -> Optional[str]:
        """
        First find the LeagueClient.exe process with psutil and read the lockfile from the executable directory.
        If not found, try hardcoded fallback paths. Cache the discovered path.
        """
        # process scan with psutil
        path = self._find_via_process()
        if path:
            self.lockfile_path = path
            return path

        # Fallback: common paths
        for fallback in FALLBACK_PATHS:
            if os.path.exists(fallback):
                self.lockfile_path = fallback
                logger.info(f"Lockfile found at fallback path: {fallback}")
                return fallback

        return None

    def _find_via_process(self) -> Optional[str]:
        """Return the lockfile path from the running LeagueClient.exe process directory."""
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    name = proc.info.get('name', '')
                    if name and name.lower() == 'leagueclient.exe':
                        exe_path = proc.info.get('exe')
                        if exe_path:
                            lockfile = os.path.join(os.path.dirname(exe_path), 'lockfile')
                            if os.path.exists(lockfile):
                                logger.info(f"Lockfile found from process: {lockfile}")
                                return lockfile
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.warning(f"Process scan error: {e}")
        return None

    # Read lockfile

    def read_lockfile(self) -> bool:
        """
        Lockfile format: LeagueClient:PID:PORT:PASSWORD:PROTOCOL
        If successful, set self.port, self.password, and self._auth_header.
        """
        if not self.lockfile_path:
            self.find_lockfile()
        if not self.lockfile_path:
            return False

        try:
            with open(self.lockfile_path, 'r') as f:
                content = f.read().strip()
            parts = content.split(':')
            if len(parts) < 5:
                logger.error(f"Invalid lockfile format: {content}")
                return False

            self.port = parts[2]
            self.password = parts[3]
            auth_str = f"riot:{self.password}".encode()
            self._auth_header = "Basic " + base64.b64encode(auth_str).decode()
            return True
        except OSError as e:
            logger.warning(f"Unable to read lockfile: {e}")
            return False

    # Readiness check

    def is_ready(self) -> bool:
        """Check whether the LoL client is ready to serve API requests."""
        if not self._auth_header:
            if not self.read_lockfile():
                return False
        # Test request
        return self.get("/lol-summoner/v1/current-summoner") is not None

    def reset(self):
        """Clear cached lockfile state (use when LoL closes and restarts)."""
        self.port = None
        self.password = None
        self.lockfile_path = None
        self._auth_header = None

    # API request

    def get(self, endpoint: str, timeout: float = 3.0) -> Optional[Any]:
        """
        Send a GET request to the LCU API. Return parsed JSON on success, otherwise None.
        If auth header is missing, try reading the lockfile first.
        """
        if not self._auth_header:
            if not self.read_lockfile():
                return None

        url = f"https://127.0.0.1:{self.port}{endpoint}"
        try:
            r = requests.get(
                url,
                headers={"Authorization": self._auth_header},
                verify=False,
                timeout=timeout,
            )
            if r.status_code == 200:
                # Some endpoints may return an empty string
                if not r.text.strip():
                    return None
                try:
                    return r.json()
                except json.JSONDecodeError:
                    return r.text
            elif r.status_code == 404:
                # Endpoint is not available at this time (e.g. /lol-lobby outside of lobby)
                return None
            else:
                logger.debug(f"LCU {endpoint} -> {r.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            # Client closed or port changed
            self.reset()
            return None
        except requests.exceptions.Timeout:
            logger.debug(f"LCU {endpoint} timeout")
            return None
        except requests.RequestException as e:
            logger.debug(f"LCU {endpoint} error: {e}")
            return None

    # High-level helpers

    def get_gameflow_phase(self) -> Optional[str]:
        """Return the current gameflow phase as a string (None, Lobby, ChampSelect, InProgress, etc.)."""
        result = self.get("/lol-gameflow/v1/gameflow-phase")
        if isinstance(result, str):
            return result.strip('"')
        return result

    def get_current_summoner(self) -> Optional[dict]:
        """Return current player information (displayName, summonerLevel, puuid, etc.)."""
        return self.get("/lol-summoner/v1/current-summoner")

    def get_ranked_stats(self) -> Optional[dict]:
        """Return ranked stats."""
        return self.get("/lol-ranked/v1/current-ranked-stats")

    def get_lobby(self) -> Optional[dict]:
        """Return current lobby info (queue ID, party size, etc.)."""
        return self.get("/lol-lobby/v2/lobby")

    def get_champ_select_session(self) -> Optional[dict]:
        """Return the champ select session (hovered champion, picks, bans)."""
        return self.get("/lol-champ-select/v1/session")

    def get_locale(self) -> Optional[str]:
        """Return the client locale (e.g. 'tr_TR', 'en_US')."""
        result = self.get("/riotclient/region-locale")
        if isinstance(result, dict):
            return result.get("locale")
        return None
