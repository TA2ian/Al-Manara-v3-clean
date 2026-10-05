from __future__ import annotations

from enum import StrEnum


class CurrencyCode(StrEnum):
    USD = "USD"
    NEW_SYP = "NEW.SYP"


_CURRENCY_ALIASES: dict[str, CurrencyCode] = {
    "USD": CurrencyCode.USD,
    "$": CurrencyCode.USD,
    "US DOLLAR": CurrencyCode.USD,
    "US DOLLARS": CurrencyCode.USD,
    "NEW.SYP": CurrencyCode.NEW_SYP,
    "NEW SYP": CurrencyCode.NEW_SYP,
    "NEW SYRIAN POUND": CurrencyCode.NEW_SYP,
    "NEW SYRIAN LIRA": CurrencyCode.NEW_SYP,
    "ليرة سورية جديدة": CurrencyCode.NEW_SYP,
    "الليرة السورية الجديدة": CurrencyCode.NEW_SYP,
    "ليرة جديدة سورية": CurrencyCode.NEW_SYP,
    "الليرة جديدة السورية": CurrencyCode.NEW_SYP,
    "الليرة الجديدة": CurrencyCode.NEW_SYP,
}


def normalize_currency(raw: str) -> CurrencyCode | None:
    normalized = " ".join(raw.strip().upper().split())
    if normalized in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[normalized]
    return None
