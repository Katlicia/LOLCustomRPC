"""
State Machine — tracks LoL game state and builds Discord RPC payloads.

All user-facing strings are resolved via the Translator (i18n).
Locale is auto-detected from the LoL client (LCU /riotclient/region-locale).
Display options are injected at construction and reloaded via apply_config().
"""

import time
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

from .lcu_client import LCUClient
from .live_client import LiveClient
from .ddragon import DDragon
from i18n.translator import Translator

logger = logging.getLogger(__name__)


class State(Enum):
    OFFLINE = "offline"
    MAIN_MENU = "main_menu"
    LOBBY = "lobby"
    MATCHMAKING = "matchmaking"
    CHAMP_SELECT = "champ_select"
    IN_GAME = "in_game"
    POST_GAME = "post_game"


PHASE_TO_STATE = {
    "None": State.MAIN_MENU,
    "Lobby": State.LOBBY,
    "Matchmaking": State.MATCHMAKING,
    "ReadyCheck": State.MATCHMAKING,
    "ChampSelect": State.CHAMP_SELECT,
    "InProgress": State.IN_GAME,
    "WaitingForStats": State.POST_GAME,
    "EndOfGame": State.POST_GAME,
    "PreEndOfGame": State.POST_GAME,
}

# Queue ID -> translation key
QUEUE_KEYS = {
    400: "queue_normal_draft",
    420: "queue_solo_duo",
    430: "queue_normal_blind",
    440: "queue_flex",
    450: "queue_aram",
    490: "queue_quickplay",
    700: "queue_clash",
    830: "queue_coop_intro",
    840: "queue_coop_beginner",
    850: "queue_coop_intermediate",
    900: "queue_urf",
    1020: "queue_one_for_all",
    1300: "queue_nexus_blitz",
    1400: "queue_spellbook",
    1700: "queue_arena",
    1900: "queue_urf",
}

# Game mode -> translation key
MODE_KEYS = {
    "CLASSIC": "mode_classic",
    "ARAM": "mode_aram",
    "URF": "mode_urf",
    "PRACTICETOOL": "mode_practice_tool",
    "TUTORIAL": "mode_tutorial",
    "ONEFORALL": "mode_one_for_all",
    "CHERRY": "mode_arena",
    "NEXUSBLITZ": "mode_nexus_blitz",
    "SWIFTPLAY": "mode_swiftplay",
}

# Live Client API position -> translation key
ROLE_KEYS = {
    "TOP": "role_top",
    "JUNGLE": "role_jungle",
    "MIDDLE": "role_mid",
    "BOTTOM": "role_adc",
    "UTILITY": "role_support",
}


@dataclass
class DisplayOptions:
    show_nick: bool = True
    show_tag: bool = True  # only takes effect when show_nick is True
    show_rank: bool = True
    show_level: bool = True
    show_kda: bool = True
    logo: str = "lol_logo"  # "lol_logo" or "lol_legacy_logo"


@dataclass
class RPCPayload:
    state_name: State
    details: str = ""
    state: Optional[str] = None
    large_image: Optional[str] = None
    large_text: Optional[str] = None
    small_image: Optional[str] = None
    small_text: Optional[str] = None
    start: Optional[int] = None

    def compute_signature(self) -> tuple:
        return (
            self.state_name.value,
            self.details,
            self.state,
            self.large_image,
            self.small_image,
        )


@dataclass
class ChampSelectHover:
    last_seen_champ_id: Optional[int] = None
    last_seen_time: float = 0.0
    last_sent_champ_id: Optional[int] = None
    DEBOUNCE_SECONDS: float = 2.0


class StateMachine:
    def __init__(
        self,
        ddragon: DDragon,
        translator: Translator,
        options: Optional[DisplayOptions] = None,
    ):
        self.lcu = LCUClient()
        self.live = LiveClient()
        self.ddragon = ddragon
        self.t = translator
        self.options = options or DisplayOptions()
        self.hover = ChampSelectHover()
        self._cached_summoner: Optional[dict] = None
        self._cached_rank: Optional[dict] = None
        self._summoner_cache_time: float = 0
        self._rank_cache_time: float = 0
        self.CACHE_DURATION = 60

        self._last_known_in_game: Optional[RPCPayload] = None
        self._in_game_start_time: float = 0
        # Last known queue ID - cached from LCU lobby/champ-select so we can
        # still show the queue type during in-game (Live Client API doesn't give it)
        self._last_known_queue_id: int = 0

        # Locale auto-detection state
        self._locale_detected: bool = False
        self._last_locale_check: float = 0
        self.LOCALE_CHECK_INTERVAL = 300  # re-check every 5 min

        self._last_reported_state: State = State.OFFLINE

    def _get_summoner_cached(self) -> Optional[dict]:
        if self._cached_summoner and (time.time() - self._summoner_cache_time) < self.CACHE_DURATION:
            return self._cached_summoner
        data = self.lcu.get_current_summoner()
        if data:
            self._cached_summoner = data
            self._summoner_cache_time = time.time()
        return self._cached_summoner

    def _get_rank_cached(self) -> Optional[dict]:
        if self._cached_rank and (time.time() - self._rank_cache_time) < self.CACHE_DURATION:
            return self._cached_rank
        data = self.lcu.get_ranked_stats()
        if data:
            self._cached_rank = data
            self._rank_cache_time = time.time()
        return self._cached_rank

    def _auto_detect_locale(self):
        """Pull locale from LCU and apply it to the translator."""
        now = time.time()
        if self._locale_detected and (now - self._last_locale_check) < self.LOCALE_CHECK_INTERVAL:
            return
        lol_locale = self.lcu.get_locale()
        if lol_locale:
            self.t.auto_detect_from_lol(lol_locale)
            if not self._locale_detected:
                logger.info(f"Locale auto-detected from LoL client: {lol_locale} -> {self.t.active_locale}")
            self._locale_detected = True
            self._last_locale_check = now

    def apply_config(self, config) -> None:
        self.options = DisplayOptions(
            show_nick=config.get("display.show_nick", True),
            show_tag=config.get("display.show_tag", True),
            show_rank=config.get("display.show_rank", True),
            show_level=config.get("display.show_level", True),
            show_kda=config.get("display.show_kda", True),
            logo=config.get("display.logo", "lol_logo"),
        )
        logger.debug(f"Options reloaded: {self.options}")

    def invalidate_caches(self):
        self._cached_summoner = None
        self._cached_rank = None
        self._summoner_cache_time = 0
        self._rank_cache_time = 0
        self.hover = ChampSelectHover()
        self._last_known_in_game = None
        self._in_game_start_time = 0
        self._last_known_queue_id = 0
        self._locale_detected = False
        self._last_reported_state = State.OFFLINE

    def detect_state(self) -> State:
        if self.live.is_in_game():
            return State.IN_GAME
        phase = self.lcu.get_gameflow_phase()
        if phase is None:
            return State.OFFLINE
        return PHASE_TO_STATE.get(phase, State.MAIN_MENU)

    def build_payload(self) -> Optional[RPCPayload]:
        state = self.detect_state()

        if state == State.OFFLINE:
            if not hasattr(self, '_last_reported_state') or self._last_reported_state != State.OFFLINE:
                logger.info("LoL client not detected — RPC cleared.")
            self._last_reported_state = State.OFFLINE
            self.invalidate_caches()
            return None

        if not hasattr(self, '_last_reported_state') or self._last_reported_state != state:
            logger.info(f"State transition: {getattr(self, '_last_reported_state', State.OFFLINE).value} -> {state.value}")
        self._last_reported_state = state

        # Locale auto-detection (only when LoL is open)
        self._auto_detect_locale()

        if state == State.IN_GAME:
            payload = self._build_ingame()
        else:
            if self._last_known_in_game is not None:
                self._last_known_in_game = None
                self._in_game_start_time = 0

            if state == State.CHAMP_SELECT:
                payload = self._build_champ_select()
            elif state == State.LOBBY:
                payload = self._build_lobby()
            elif state == State.MATCHMAKING:
                payload = self._build_matchmaking()
            elif state == State.POST_GAME:
                payload = self._build_post_game()
            else:
                payload = self._build_main_menu()

        if payload:
            self._apply_user_avatar(payload)

        return payload

    def _apply_user_avatar(self, payload: RPCPayload):
        """Always attach the user's LoL profile avatar as small_image.
        Hover text respects the same nick/tag/rank toggles as the payload."""
        summoner = self._get_summoner_cached() or {}
        icon_id = summoner.get("profileIconId", 0)
        if not icon_id:
            return

        avatar_url = self.ddragon.profile_icon(icon_id)
        rank_data = self._get_rank_cached() or {}

        hover_parts = []

        nick_display = self._get_display_name_with_toggles(summoner)
        if nick_display:
            hover_parts.append(nick_display)

        if self.options.show_rank:
            rank_text = self._format_rank(rank_data)
            unranked_label = self.t.t("rank_unranked")
            if rank_text and rank_text != unranked_label:
                hover_parts.append(rank_text)

        hover_text = " • ".join(hover_parts) or None

        payload.small_image = avatar_url
        payload.small_text = hover_text

    # Builders

    def _build_main_menu(self) -> RPCPayload:
        summoner = self._get_summoner_cached() or {}
        rank_data = self._get_rank_cached() or {}
        level = summoner.get("summonerLevel", 0)

        details_parts = self._user_info_parts(summoner, rank_data)
        if level and self.options.show_level:
            details_parts.append(self.t.t("level_format", level=level))

        return RPCPayload(
            state_name=State.MAIN_MENU,
            details=self.t.t("in_main_menu"),
            state=" | ".join(details_parts) or None,
            large_image=self.options.logo,
            large_text="League of Legends",
        )

    def _build_lobby(self) -> RPCPayload:
        summoner = self._get_summoner_cached() or {}
        lobby = self.lcu.get_lobby() or {}
        rank_data = self._get_rank_cached() or {}

        queue_id = lobby.get("gameConfig", {}).get("queueId", 0)
        if queue_id:
            self._last_known_queue_id = queue_id  # cache for later in-game use
        queue_label = self._queue_label(queue_id)

        members = lobby.get("members", [])
        party_size = len(members) if members else 1

        if party_size > 1:
            details = self.t.t("in_lobby_party", queue=queue_label, size=party_size)
        else:
            details = self.t.t("in_lobby", queue=queue_label)

        state_parts = self._user_info_parts(summoner, rank_data)

        return RPCPayload(
            state_name=State.LOBBY,
            details=details,
            state=" | ".join(state_parts) or None,
            large_image=self.options.logo,
            large_text="League of Legends",
        )

    def _build_matchmaking(self) -> RPCPayload:
        summoner = self._get_summoner_cached() or {}
        rank_data = self._get_rank_cached() or {}
        lobby = self.lcu.get_lobby() or {}

        queue_id = lobby.get("gameConfig", {}).get("queueId", 0)
        if queue_id:
            self._last_known_queue_id = queue_id
        queue_label = self._queue_label(queue_id)

        state_parts = self._user_info_parts(summoner, rank_data)

        return RPCPayload(
            state_name=State.MATCHMAKING,
            details=self.t.t("in_queue", queue=queue_label),
            state=" | ".join(state_parts) or None,
            large_image=self.options.logo,
            large_text="League of Legends",
        )

    def _build_champ_select(self) -> RPCPayload:
        session = self.lcu.get_champ_select_session() or {}
        my_champion_id = self._extract_my_champion(session)

        # Queue ID - cache for in-game use
        queue_id = session.get("gameId", 0) and 0  # session doesn't expose queueId directly
        # Pull from lobby instead (more reliable)
        lobby = self.lcu.get_lobby() or {}
        queue_id = lobby.get("gameConfig", {}).get("queueId", 0)
        if queue_id:
            self._last_known_queue_id = queue_id
        queue_label = self._queue_label(queue_id) if queue_id else ""

        now = time.time()
        if my_champion_id != self.hover.last_seen_champ_id:
            self.hover.last_seen_champ_id = my_champion_id
            self.hover.last_seen_time = now
            display_champ_id = self.hover.last_sent_champ_id
        else:
            if (now - self.hover.last_seen_time) >= self.hover.DEBOUNCE_SECONDS:
                self.hover.last_sent_champ_id = my_champion_id
                display_champ_id = my_champion_id
            else:
                display_champ_id = self.hover.last_sent_champ_id

        summoner = self._get_summoner_cached() or {}
        rank_data = self._get_rank_cached() or {}

        state_parts = self._user_info_parts(summoner, rank_data)

        if display_champ_id and display_champ_id > 0:
            large_image = self.ddragon.champion_icon_by_id(display_champ_id)
        else:
            large_image = self.options.logo

        # details: "Picking champion - Solo/Duo" (if queue known)
        if queue_label:
            details = f"{self.t.t('picking_champion')} - {queue_label}"
        else:
            details = self.t.t("picking_champion")

        return RPCPayload(
            state_name=State.CHAMP_SELECT,
            details=details,
            state=" | ".join(state_parts) or None,
            large_image=large_image,
            large_text="League of Legends",
        )

    def _build_ingame(self) -> Optional[RPCPayload]:
        all_data = self.live.get_all_data()

        if not all_data:
            if self._last_known_in_game:
                return self._last_known_in_game
            return RPCPayload(
                state_name=State.IN_GAME,
                details=self.t.t("in_match"),
                state=self.t.t("loading"),
                large_image=self.options.logo,
                large_text="League of Legends",
                start=int(time.time()),
            )

        me = self.live.find_me_in_players(all_data)
        if not me:
            if self._last_known_in_game:
                return self._last_known_in_game
            return None

        champion = me.get("championName", "")
        skin_id = me.get("skinID", 0)
        position = me.get("position", "")
        role_text = self._role_label(position)

        scores = me.get("scores", {})
        k = scores.get("kills", 0)
        d = scores.get("deaths", 0)
        a = scores.get("assists", 0)

        game_data = all_data.get("gameData", {})
        game_mode = game_data.get("gameMode", "CLASSIC")
        game_time = game_data.get("gameTime", 0)
        mode_label = self._mode_label(game_mode)

        if game_time > 0:
            if self._in_game_start_time == 0:
                self._in_game_start_time = time.time() - game_time
            start_ts = int(self._in_game_start_time)
        else:
            if self._in_game_start_time == 0:
                self._in_game_start_time = time.time()
            start_ts = int(self._in_game_start_time)

        champion_id = self.hover.last_sent_champ_id
        if not champion_id and champion:
            champion_id = self.ddragon.get_champion_id(champion)

        large_image = None
        if champion_id and champion_id > 0:
            large_image = self.ddragon.get_skin_image(champion_id, skin_id, prefer="tile")
        if not large_image and champion:
            large_image = self.ddragon.champion_loading(champion, skin_id)
        if not large_image:
            large_image = self.options.logo

        large_text = champion if champion else "League of Legends"

        # State line: KDA + optional role
        if self.options.show_kda:
            if role_text:
                state_text = self.t.t("kda_with_role", k=k, d=d, a=a, role=role_text)
            else:
                state_text = self.t.t("kda_format", k=k, d=d, a=a)
        else:
            state_text = role_text or None

        # details: "Champion - Queue (if known) - Mode"
        # Examples:
        #   "Aphelios - Solo/Duo"          (ranked solo/duo on SR)
        #   "Yasuo - ARAM"                 (ARAM)
        #   "Lux - Practice Tool"          (no queue, just mode)
        # Prefer queue type over generic mode name when available
        queue_label = self._queue_label(self._last_known_queue_id) if self._last_known_queue_id else ""

        if champion and queue_label:
            details = f"{champion} - {queue_label}"
        elif champion:
            details = f"{champion} - {mode_label}"
        else:
            details = mode_label

        payload = RPCPayload(
            state_name=State.IN_GAME,
            details=details,
            state=state_text,
            large_image=large_image,
            large_text=large_text,
            start=start_ts,
        )

        self._last_known_in_game = payload
        return payload

    def _build_post_game(self) -> RPCPayload:
        summoner = self._get_summoner_cached() or {}
        rank_data = self._get_rank_cached() or {}
        state_parts = self._user_info_parts(summoner, rank_data)
        return RPCPayload(
            state_name=State.POST_GAME,
            details=self.t.t("match_ended"),
            state=" | ".join(state_parts) or None,
            large_image=self.options.logo,
            large_text="League of Legends",
        )

    # Display helpers that respect toggles

    def _user_info_parts(self, summoner: dict, rank_data: dict) -> list:
        """
        Build a list of display strings honoring nick/tag/rank toggles.
        Used to fill the `state` line consistently across builders.
        Returns e.g. ["Hide on bush#KR1", "Challenger 1500LP"] depending on toggles.
        """
        parts = []
        nick_display = self._get_display_name_with_toggles(summoner)
        if nick_display:
            parts.append(nick_display)

        if self.options.show_rank:
            rank_text = self._format_rank(rank_data)
            unranked_label = self.t.t("rank_unranked")
            if rank_text and rank_text != unranked_label:
                parts.append(rank_text)

        return parts

    def _get_display_name_with_toggles(self, summoner: dict) -> str:
        """
        Apply show_nick + show_tag toggles.
        - show_nick=False -> returns ""
        - show_nick=True, show_tag=False -> "Hide on bush"
        - show_nick=True, show_tag=True -> "Hide on bush#KR1"
        """
        if not self.options.show_nick:
            return ""
        if not summoner:
            return ""
        game_name = summoner.get("gameName") or summoner.get("displayName") or ""
        tag = summoner.get("tagLine", "")
        if not game_name:
            game_name = summoner.get("internalName", "")
        if game_name and tag and self.options.show_tag:
            return f"{game_name}#{tag}"
        return game_name

    # Localized lookups

    def _queue_label(self, queue_id: int) -> str:
        key = QUEUE_KEYS.get(queue_id)
        if key:
            return self.t.t(key)
        return self.t.t("queue_custom")

    def _mode_label(self, mode: str) -> str:
        key = MODE_KEYS.get(mode)
        if key:
            return self.t.t(key)
        return mode

    def _role_label(self, position: str) -> str:
        if not position:
            return ""
        key = ROLE_KEYS.get(position.upper())
        if key:
            return self.t.t(key)
        return position.capitalize()

    # Other helpers

    def _format_rank(self, rank_data: dict) -> str:
        if not rank_data:
            return self.t.t("rank_unranked")
        queues = rank_data.get("queues", [])
        for q in queues:
            if q.get("queueType") == "RANKED_SOLO_5x5":
                tier = q.get("tier", "")
                division = q.get("division", "")
                if tier and tier.upper() not in ("NONE", "UNRANKED", ""):
                    tier_display = tier.capitalize()
                    if division and division != "NA":
                        return self.t.t("rank_format", tier=tier_display, division=division)
                    return self.t.t("rank_format_no_division", tier=tier_display)
        return self.t.t("rank_unranked")

    @staticmethod
    def _extract_my_champion(session: dict) -> Optional[int]:
        if not session:
            return None
        local_cell_id = session.get("localPlayerCellId", -1)
        for action_group in session.get("actions", []):
            for action in action_group:
                if action.get("actorCellId") == local_cell_id and action.get("type") == "pick":
                    cid = action.get("championId", 0)
                    if cid > 0:
                        return cid
        for member in session.get("myTeam", []):
            if member.get("cellId") == local_cell_id:
                cid = member.get("championId", 0)
                if cid > 0:
                    return cid
        return None
