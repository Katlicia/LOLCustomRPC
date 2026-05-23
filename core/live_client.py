"""
Live Client Data API client.
- Runs on port 2999 on localhost
- Only active while the user is in a match
- Uses a self-signed certificate, so verify=False is required
"""

import logging
from typing import Optional, Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE_URL = "https://127.0.0.1:2999/liveclientdata"


class LiveClient:
    """Wrapper for the Live Client Data API (in-match data)."""

    def get(self, endpoint: str, timeout: float = 2.0) -> Optional[Any]:
        """GET request. Returns None when not in a match."""
        try:
            r = requests.get(
                f"{BASE_URL}{endpoint}",
                verify=False,
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.json()
            return None
        except requests.exceptions.ConnectionError:
            return None
        except requests.exceptions.Timeout:
            return None
        except requests.RequestException as e:
            logger.debug(f"LiveClient {endpoint} error: {e}")
            return None

    def is_in_game(self) -> bool:
        """True if the Live Client Data API is reachable (i.e. a match is in progress)."""
        data = self.get("/gamestats", timeout=1.5)
        return data is not None

    def get_all_data(self) -> Optional[dict]:
        """Full game snapshot (players, active player, game time, etc.)."""
        return self.get("/allgamedata")

    def get_active_player(self) -> Optional[dict]:
        """Detailed data for the local player."""
        return self.get("/activeplayer")

    def get_active_player_name(self) -> Optional[str]:
        """Riot ID or summoner name of the local player."""
        result = self.get("/activeplayername")
        if isinstance(result, str):
            return result.strip('"')
        return result

    def get_player_list(self) -> Optional[list]:
        """List of all players in the match (includes skin ID)."""
        return self.get("/playerlist")

    def get_game_stats(self) -> Optional[dict]:
        """Game mode and elapsed time."""
        return self.get("/gamestats")

    # Player lookup

    def find_me_in_players(self, all_data: dict) -> Optional[dict]:
        """
        Locate the local player in allgamedata by matching
        activePlayer.riotIdGameName against allPlayers entries.
        Falls back to the first player if no match (spectator scenario).
        """
        active = all_data.get("activePlayer", {})
        my_name = active.get("summonerName") or active.get("riotIdGameName") or ""

        my_game_name = my_name.split("#")[0] if "#" in my_name else my_name

        for player in all_data.get("allPlayers", []):
            riot_name = player.get("riotIdGameName", "")
            summoner_name = player.get("summonerName", "")
            if (riot_name and riot_name == my_game_name) or (summoner_name and summoner_name == my_name):
                return player

        players = all_data.get("allPlayers", [])
        return players[0] if players else None
