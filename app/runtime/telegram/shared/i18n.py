import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

current_lang: ContextVar[str] = ContextVar("current_lang", default="ar")

class I18nService:
    def __init__(self, locale_dir: str):
        self.locale_dir = Path(locale_dir)
        self._translations: dict[str, dict[str, str]] = {}
        self.load_translations()

    def load_translations(self):
        for lang_file in self.locale_dir.glob("*.json"):
            lang_code = lang_file.stem
            with open(lang_file, "r", encoding="utf-8") as f:
                self._translations[lang_code] = json.load(f)

    def get(self, key: str, **kwargs: Any) -> str:
        lang = current_lang.get()
        text = self._translations.get(lang, {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text

# A global instance can be configured later
i18n_instance: I18nService | None = None

def get_text(key: str, **kwargs: Any) -> str:
    if i18n_instance is None:
        return key
    return i18n_instance.get(key, **kwargs)
