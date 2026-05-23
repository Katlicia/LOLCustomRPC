"""
i18n Translator.

Loads locale JSON files and provides string lookup by key.
Supports format() substitution: t("kda_format", k=5, d=2, a=3) -> "KDA: 5/2/3"

Locale resolution:
- Pass "auto" to use the LoL client locale (fetched via LCU)
- Pass a specific code: "tr", "en", "es", etc.
- Falls back to English if key is missing in selected locale
- Falls back to the key itself if missing in English too (so devs notice)

Locale file format: i18n/locales/{lang}.json
  {
    "in_main_menu": "In main menu",
    "kda_format": "KDA: {k}/{d}/{a}",
    ...
  }
"""

import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# LoL locale code -> our locale file name
# LoL returns codes like "tr_TR", "en_US", "en_GB", "es_ES", "es_MX", "pt_BR"
# We collapse them to language-only since translations don't change per region
LOL_LOCALE_MAP = {
    "tr_tr": "tr",
    "en_us": "en",
    "en_gb": "en",
    "en_au": "en",
    "en_ph": "en",
    "en_sg": "en",
    "es_es": "es",
    "es_mx": "es",
    "es_ar": "es",
    "pt_br": "pt",
    "fr_fr": "fr",
    "de_de": "de",
    "it_it": "it",
    "pl_pl": "pl",
    "ru_ru": "ru",
    "el_gr": "el",
    "ro_ro": "ro",
    "hu_hu": "hu",
    "cs_cz": "cs",
    "ja_jp": "ja",
    "ko_kr": "ko",
    "zh_cn": "zh",
    "zh_tw": "zh",
    "vi_vn": "vi",
    "th_th": "th",
}

DEFAULT_LOCALE = "en"


def _locales_dir() -> str:
    """Folder containing locale JSON files."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")


class Translator:
    def __init__(self, locale: str = "auto"):
        """
        locale: "auto" (use LoL client locale at runtime) or a specific language code.
        """
        self._configured_locale: str = locale
        self._active_locale: str = DEFAULT_LOCALE
        self._auto_locale: str = DEFAULT_LOCALE  # last locale detected from LCU
        self._strings: Dict[str, str] = {}
        self._fallback_strings: Dict[str, str] = {}
        self._load_fallback()
        if locale != "auto":
            self.set_locale(locale)

    def _load_fallback(self):
        """Always keep English loaded as the safety net."""
        path = os.path.join(_locales_dir(), f"{DEFAULT_LOCALE}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._fallback_strings = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Could not load fallback locale {DEFAULT_LOCALE}: {e}")
                self._fallback_strings = {}

    def set_locale(self, locale: str) -> bool:
        """
        Load the given locale file. Returns True on success.
        If the file doesn't exist, keeps the previous locale and returns False.
        """
        if not locale:
            return False
        locale_lower = locale.lower()

        # Convert from LoL format if needed (en_GB -> en)
        if locale_lower in LOL_LOCALE_MAP:
            locale_lower = LOL_LOCALE_MAP[locale_lower]

        # If the same locale is already loaded, don't reload
        if locale_lower == self._active_locale and self._strings:
            return True

        path = os.path.join(_locales_dir(), f"{locale_lower}.json")
        if not os.path.exists(path):
            logger.warning(f"Locale file not found: {path} (falling back to {DEFAULT_LOCALE})")
            self._active_locale = DEFAULT_LOCALE
            self._strings = dict(self._fallback_strings)
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._strings = json.load(f)
            self._active_locale = locale_lower
            logger.info(f"Locale switched to: {locale_lower}")
            return True
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Could not load locale {locale_lower}: {e}")
            return False

    def auto_detect_from_lol(self, lol_locale: Optional[str]):
        """
        Set locale based on a code received from LCU (e.g. "tr_TR").
        Only applies if the user configured "auto".
        """
        if self._configured_locale != "auto":
            return
        if not lol_locale:
            return
        self.set_locale(lol_locale)
        self._auto_locale = self._active_locale  # remember for UI "auto" revert

    @property
    def active_locale(self) -> str:
        return self._active_locale

    @property
    def auto_locale(self) -> str:
        """Last locale resolved from the LoL client (used by UI to revert to 'auto')."""
        return self._auto_locale

    def t(self, key: str, **kwargs) -> str:
        """
        Look up `key` in the active locale, then English, then return the key itself.
        Supports str.format() substitution via kwargs.
        """
        template = self._strings.get(key)
        if template is None:
            template = self._fallback_strings.get(key, key)

        if kwargs:
            try:
                return template.format(**kwargs)
            except (KeyError, IndexError, ValueError) as e:
                logger.warning(f"Format error for '{key}' with {kwargs}: {e}")
                return template
        return template
