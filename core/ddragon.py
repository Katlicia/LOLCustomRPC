"""
Data Dragon (DDragon) + Community Dragon integration.

IMPORTANT:
- Champion square icon: CDragon /v1/champion-icons/{id}.png (working, stable endpoint)
- Profile icon (user avatar): CDragon /v1/profile-icons/{id}.jpg
- Skin images: EACH SKIN HAS A DIFFERENT PATH! Fetched from /v1/champions/{id}.json
  - tilePath: square format (ideal for Discord)
  - splashPath: centered wide splash
  - uncenteredSplashPath: uncentered original composition
- These paths come in /lol-game-data/assets/... format
- For CDragon URLs: remove prefix and lowercase the whole path
"""

import time
import logging
from typing import Optional, Dict, Tuple

import requests

logger = logging.getLogger(__name__)

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_BASE = "https://ddragon.leagueoflegends.com/cdn"
CDRAGON_BASE = "https://raw.communitydragon.org/latest"
CDRAGON_DATA_BASE = f"{CDRAGON_BASE}/plugins/rcp-be-lol-game-data/global/default"
CDRAGON_CHAMPIONS_URL = f"{CDRAGON_DATA_BASE}/v1/champion-summary.json"

FALLBACK_VERSION = "14.24.1"
CACHE_DURATION = 24 * 60 * 60

NAME_MAP = {
    "Wukong": "MonkeyKing",
    "Nunu & Willump": "Nunu",
    "Renata Glasc": "Renata",
    "Cho'Gath": "Chogath",
    "Kai'Sa": "Kaisa",
    "Kha'Zix": "Khazix",
    "Kog'Maw": "KogMaw",
    "LeBlanc": "Leblanc",
    "Vel'Koz": "Velkoz",
    "Bel'Veth": "Belveth",
    "Rek'Sai": "RekSai",
    "Dr. Mundo": "DrMundo",
    "Jarvan IV": "JarvanIV",
    "Master Yi": "MasterYi",
    "Miss Fortune": "MissFortune",
    "Tahm Kench": "TahmKench",
    "Twisted Fate": "TwistedFate",
    "Aurelion Sol": "AurelionSol",
    "Lee Sin": "LeeSin",
    "Xin Zhao": "XinZhao",
    "K'Sante": "KSante",
}

ROLE_NAMES = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Mid",
    "BOTTOM": "ADC",
    "UTILITY": "Support",
    "NONE": "",
    "": "",
}


def _asset_path_to_url(asset_path: str) -> str:
    """
    /lol-game-data/assets/ASSETS/Characters/.../foo.jpg
    -> https://raw.communitydragon.org/latest/plugins/.../assets/characters/.../foo.jpg
    """
    if not asset_path:
        return ""
    # remove /lol-game-data/assets/ prefix and lowercase the path
    clean = asset_path.lower()
    if clean.startswith("/lol-game-data/assets/"):
        clean = clean[len("/lol-game-data/assets/"):]
    return f"{CDRAGON_DATA_BASE}/{clean}"


class DDragon:
    def __init__(self):
        self._version: Optional[str] = None
        self._version_cached_at: float = 0
        # Champion ID <-> name mapping (both directions)
        self._champion_name_to_id: Dict[str, int] = {}
        self._champion_id_to_name: Dict[int, str] = {}
        self._champions_cached_at: float = 0
        # Per-champion skin path cache: (champ_id, skin_id) -> {tile, splash, uncentered}
        self._skin_paths_cache: Dict[Tuple[int, int], Dict[str, str]] = {}
        # Which champion_ids have had their JSON loaded (skins cached)
        self._champion_skins_loaded: set = set()

    # Version management

    @property
    def version(self) -> str:
        if self._version and (time.time() - self._version_cached_at) < CACHE_DURATION:
            return self._version
        self._refresh_version()
        return self._version or FALLBACK_VERSION

    def _refresh_version(self):
        try:
            r = requests.get(VERSIONS_URL, timeout=5)
            if r.status_code == 200:
                versions = r.json()
                if versions and isinstance(versions, list):
                    self._version = versions[0]
                    self._version_cached_at = time.time()
                    logger.info(f"DDragon version: {self._version}")
                    return
        except Exception as e:
            logger.warning(f"DDragon version fetch error: {e}")
        if not self._version:
            self._version = FALLBACK_VERSION

    # Champion list (name <-> id mapping)

    def _refresh_champions(self):
        """Fetch all champions ID+name list (CDragon first, DDragon fallback)."""
        # 1) CDragon
        try:
            r = requests.get(CDRAGON_CHAMPIONS_URL, timeout=8)
            if r.status_code == 200:
                champions = r.json()
                self._champion_name_to_id = {}
                self._champion_id_to_name = {}
                for c in champions:
                    cid = c.get("id", 0)
                    if cid <= 0:
                        continue
                    name = c.get("name", "")
                    alias = c.get("alias", "")
                    if name:
                        self._champion_name_to_id[name] = cid
                        self._champion_id_to_name[cid] = name
                    if alias and alias != name:
                        self._champion_name_to_id[alias] = cid
                self._champions_cached_at = time.time()
                logger.info(f"Champion list from CDragon: {len(self._champion_id_to_name)} entries")
                return
        except Exception as e:
            logger.warning(f"CDragon champion list error: {e}")

        # DDragon fallback
        try:
            url = f"{DDRAGON_BASE}/{self.version}/data/en_US/champion.json"
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json().get("data", {})
                self._champion_name_to_id = {}
                self._champion_id_to_name = {}
                for key, c in data.items():
                    try:
                        cid = int(c.get("key", 0))
                    except (ValueError, TypeError):
                        continue
                    if cid <= 0:
                        continue
                    name = c.get("name", "")
                    if name:
                        self._champion_name_to_id[name] = cid
                        self._champion_id_to_name[cid] = name
                    if key and key != name:
                        self._champion_name_to_id[key] = cid
                self._champions_cached_at = time.time()
                logger.info(f"Champion list from DDragon: {len(self._champion_id_to_name)} entries")
        except Exception as e:
            logger.warning(f"DDragon champion list error: {e}")

    def get_champion_id(self, name: str) -> Optional[int]:
        """Convert a champion name to its ID."""
        if not name:
            return None
        if not self._champion_name_to_id or (time.time() - self._champions_cached_at) > CACHE_DURATION:
            self._refresh_champions()
        if name in self._champion_name_to_id:
            return self._champion_name_to_id[name]
        mapped = NAME_MAP.get(name)
        if mapped and mapped in self._champion_name_to_id:
            return self._champion_name_to_id[mapped]
        cleaned = self.normalize_champion_name(name)
        if cleaned in self._champion_name_to_id:
            return self._champion_name_to_id[cleaned]
        return None

    # Per-champion skin paths

    def _load_champion_skins(self, champion_id: int) -> bool:
        """
        Fetch a champion's JSON and cache all skin paths.
        Once loaded, all skins are available.
        """
        if champion_id in self._champion_skins_loaded:
            return True
        url = f"{CDRAGON_DATA_BASE}/v1/champions/{champion_id}.json"
        try:
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                logger.warning(f"Could not fetch champion {champion_id} JSON: {r.status_code}")
                return False
            data = r.json()
            for skin in data.get("skins", []):
                # Skin ID format: champ_id*1000 + skin_index (e.g. 28006 = Eve K/DA)
                skin_full_id = skin.get("id", 0)
                skin_index = skin_full_id - (champion_id * 1000) if skin_full_id >= champion_id * 1000 else skin_full_id
                paths = {
                    "tile": _asset_path_to_url(skin.get("tilePath", "")),
                    "splash": _asset_path_to_url(skin.get("splashPath", "")),
                    "uncentered": _asset_path_to_url(skin.get("uncenteredSplashPath", "")),
                    "load": _asset_path_to_url(skin.get("loadScreenPath", "")),
                }
                self._skin_paths_cache[(champion_id, skin_index)] = paths
            self._champion_skins_loaded.add(champion_id)
            logger.info(f"Champion {champion_id} skins loaded: {len([k for k in self._skin_paths_cache if k[0]==champion_id])} skins")
            return True
        except Exception as e:
            logger.warning(f"Champion {champion_id} skin loading error: {e}")
            return False

    def get_skin_image(self, champion_id: int, skin_index: int = 0, prefer: str = "tile") -> Optional[str]:
        """
        Image URL for a champion + skin.
        prefer: 'tile' (square, ideal for Discord) | 'splash' (centered) | 'uncentered' | 'load'
        Falls back to base skin (0) if the requested path is missing.
        """
        if not champion_id or champion_id <= 0:
            return None

        # If cached, return directly
        key = (champion_id, skin_index)
        if key in self._skin_paths_cache:
            url = self._skin_paths_cache[key].get(prefer)
            if url:
                return url

        # If not cached, load it
        if champion_id not in self._champion_skins_loaded:
            self._load_champion_skins(champion_id)

        if key in self._skin_paths_cache:
            url = self._skin_paths_cache[key].get(prefer)
            if url:
                return url

        # This skin is missing, fall back to base skin
        if skin_index != 0:
            base_key = (champion_id, 0)
            if base_key in self._skin_paths_cache:
                return self._skin_paths_cache[base_key].get(prefer)

        return None

    # URL builders

    @staticmethod
    def normalize_champion_name(name: str) -> str:
        if not name:
            return ""
        if name in NAME_MAP:
            return NAME_MAP[name]
        return name.replace(" ", "").replace("'", "").replace(".", "").replace("&", "")

    def champion_icon(self, name: str) -> str:
        """DDragon square icon by champion name."""
        norm = self.normalize_champion_name(name)
        return f"{DDRAGON_BASE}/{self.version}/img/champion/{norm}.png"

    def champion_icon_by_id(self, champion_id: int) -> str:
        """CDragon square icon by champion ID (guaranteed to work in champ select)."""
        return f"{CDRAGON_DATA_BASE}/v1/champion-icons/{champion_id}.png"

    def profile_icon(self, icon_id: int) -> str:
        """
        User's profile icon (avatar).
        Using CDragon because it's version-agnostic and more reliable than DDragon's
        version-bound paths.
        """
        if not icon_id or icon_id <= 0:
            icon_id = 29  # Default unknown icon
        return f"{CDRAGON_DATA_BASE}/v1/profile-icons/{icon_id}.jpg"

    def champion_loading(self, name: str, skin_id: int = 0) -> str:
        """DDragon loading art (skin supported)."""
        norm = self.normalize_champion_name(name)
        return f"{DDRAGON_BASE}/img/champion/loading/{norm}_{skin_id}.jpg"

    def champion_splash(self, name: str, skin_id: int = 0) -> str:
        """DDragon splash art (skin supported, horizontal)."""
        norm = self.normalize_champion_name(name)
        return f"{DDRAGON_BASE}/img/champion/splash/{norm}_{skin_id}.jpg"

    def rank_emblem(self, tier: str) -> str:
        if not tier or tier.upper() in ("NONE", "UNRANKED", ""):
            tier_lower = "unranked"
        else:
            tier_lower = tier.lower()
        return f"{CDRAGON_BASE}/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-emblem/emblem-{tier_lower}.png"


def format_role(position: str) -> str:
    if not position:
        return ""
    return ROLE_NAMES.get(position.upper(), position.capitalize())