"""
Live Client Data API client.
- runs on https://127.0.0.1:2999
- only active when the user is in a match
- uses self-signed SSL, so verify=False is required
"""

import logging
from typing import Optional, Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE_URL = "https://127.0.0.1:2999/liveclientdata"


class LiveClient:
    """Wrapper for Live Client Data API used for in-game data."""

    def get(self, endpoint: str, timeout: float = 2.0) -> Optional[Any]:
        """Send a GET request. Returns None if there is no response (e.g. outside a match)."""
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
            # Not in a match, expected
            return None
        except requests.exceptions.Timeout:
            return None
        except requests.RequestException as e:
            logger.debug(f"LiveClient {endpoint} error: {e}")
            return None

    def is_in_game(self) -> bool:
        """Check whether the user is currently in a game."""
        data = self.get("/gamestats", timeout=1.5)
        return data is not None

    def get_all_data(self) -> Optional[dict]:
        """Return all game data (players, active player, game time, etc.)."""
        return self.get("/allgamedata")

    def get_active_player(self) -> Optional[dict]:
        """Return detailed data for the active player (the user)."""
        return self.get("/activeplayer")

    def get_active_player_name(self) -> Optional[str]:
        """Return the active player's name (Riot ID or summoner name)."""
        result = self.get("/activeplayername")
        if isinstance(result, str):
            return result.strip('"')
        return result

    def get_player_list(self) -> Optional[list]:
        """Return the list of all players (including skin ID)."""
        return self.get("/playerlist")

    def get_game_stats(self) -> Optional[dict]:
        """Return game mode and time."""
        return self.get("/gamestats")

    # Find active player

    def find_me_in_players(self, all_data: dict) -> Optional[dict]:
        """
        Find the user's player entry in allgamedata.
        Matches activePlayer.summonerName with allPlayers riotIdGameName.
        """
        active = all_data.get("activePlayer", {})
        my_name = active.get("summonerName") or active.get("riotIdGameName") or ""

        # Riot ID may arrive in Name#TAG format
        my_game_name = my_name.split("#")[0] if "#" in my_name else my_name

        for player in all_data.get("allPlayers", []):
            riot_name = player.get("riotIdGameName", "")
            summoner_name = player.get("summonerName", "")
            if (riot_name and riot_name == my_game_name) or (summoner_name and summoner_name == my_name):
                return player

        # If not found, use the first player (spectator scenario)
        players = all_data.get("allPlayers", [])
        return players[0] if players else None
