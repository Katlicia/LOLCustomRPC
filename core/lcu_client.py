"""
LCU (League Client Update) API client.
- Finds the LeagueClient.exe process via psutil and reads the lockfile path from it
- Falls back to common hardcoded paths if psutil scan fails
- Reads port + password from the lockfile and authenticates with Basic Auth over HTTPS
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

    # Lockfile discovery

    def find_lockfile(self) -> Optional[str]:
        """
        Scan for LeagueClient.exe via psutil first; fall back to hardcoded paths.
        Caches the found path in self.lockfile_path.
        """
        path = self._find_via_process()
        if path:
            self.lockfile_path = path
            return path

        for fallback in FALLBACK_PATHS:
            if os.path.exists(fallback):
                self.lockfile_path = fallback
                logger.info(f"Lockfile found at fallback path: {fallback}")
                return fallback

        logger.debug("Lockfile not found — League client is probably not running.")
        return None

    def _find_via_process(self) -> Optional[str]:
        """Derive the lockfile path from the running LeagueClient.exe process."""
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    name = proc.info.get('name', '')
                    if name and name.lower() == 'leagueclient.exe':
                        exe_path = proc.info.get('exe')
                        if exe_path:
                            lockfile = os.path.join(os.path.dirname(exe_path), 'lockfile')
                            if os.path.exists(lockfile):
                                logger.info(f"Lockfile found via process: {lockfile}")
                                return lockfile
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.warning(f"Process scan error: {e}")
        return None

    # Lockfile parsing

    def read_lockfile(self) -> bool:
        """
        Lockfile format: LeagueClient:PID:PORT:PASSWORD:PROTOCOL
        Sets self.port, self.password, and self._auth_header on success.
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
                logger.error(f"Lockfile has unexpected format: {content}")
                return False

            self.port = parts[2]
            self.password = parts[3]
            auth_str = f"riot:{self.password}".encode()
            self._auth_header = "Basic " + base64.b64encode(auth_str).decode()
            logger.info(f"Lockfile read — port: {self.port}")
            return True
        except OSError as e:
            logger.warning(f"Could not read lockfile: {e}")
            return False

    # Readiness check

    def is_ready(self) -> bool:
        """Return True if the LCU API is reachable and responding."""
        if not self._auth_header:
            if not self.read_lockfile():
                return False
        return self.get("/lol-summoner/v1/current-summoner") is not None

    def reset(self):
        """Clear cached credentials (call when the client process restarts)."""
        logger.debug("LCU credentials reset.")
        self.port = None
        self.password = None
        self.lockfile_path = None
        self._auth_header = None

    # HTTP

    def get(self, endpoint: str, timeout: float = 3.0) -> Optional[Any]:
        """
        GET an LCU endpoint. Returns parsed JSON on 200, None otherwise.
        Automatically reads the lockfile if credentials are not yet set.
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
                if not r.text.strip():
                    return None
                try:
                    return r.json()
                except json.JSONDecodeError:
                    return r.text
            elif r.status_code == 404:
                return None
            else:
                logger.debug(f"LCU {endpoint} -> HTTP {r.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            self.reset()
            return None
        except requests.exceptions.Timeout:
            logger.debug(f"LCU {endpoint} timed out.")
            return None
        except requests.RequestException as e:
            logger.debug(f"LCU {endpoint} request error: {e}")
            return None

    # High-level helpers

    def get_gameflow_phase(self) -> Optional[str]:
        """Current gameflow phase string (None, Lobby, ChampSelect, InProgress, etc.)."""
        result = self.get("/lol-gameflow/v1/gameflow-phase")
        if isinstance(result, str):
            return result.strip('"')
        return result

    def get_current_summoner(self) -> Optional[dict]:
        """Current player info (displayName, summonerLevel, puuid, etc.)."""
        return self.get("/lol-summoner/v1/current-summoner")

    def get_ranked_stats(self) -> Optional[dict]:
        """Current ranked statistics."""
        return self.get("/lol-ranked/v1/current-ranked-stats")

    def get_lobby(self) -> Optional[dict]:
        """Current lobby info (queue ID, party size, etc.)."""
        return self.get("/lol-lobby/v2/lobby")

    def get_champ_select_session(self) -> Optional[dict]:
        """Current champion select session (hovered champion, picks, bans)."""
        return self.get("/lol-champ-select/v1/session")

    def get_locale(self) -> Optional[str]:
        """Client locale string (e.g. 'tr_TR', 'en_US')."""
        result = self.get("/riotclient/region-locale")
        if isinstance(result, dict):
            return result.get("locale")
        return None
