from app.domain.currency import CurrencyCode, normalize_currency


def test_new_syp_arabic_aliases_normalize_to_internal_code() -> None:
    values = (
        "ليرة سورية جديدة",
        "الليرة السورية الجديدة",
        "ليرة جديدة سورية",
        "الليرة الجديدة",
    )
    for value in values:
        assert normalize_currency(value) is CurrencyCode.NEW_SYP


def test_new_syp_english_aliases_normalize_to_internal_code() -> None:
    assert normalize_currency("New SYP") is CurrencyCode.NEW_SYP
    assert normalize_currency("New Syrian Pound") is CurrencyCode.NEW_SYP
    assert normalize_currency("New Syrian Lira") is CurrencyCode.NEW_SYP


def test_unknown_currency_is_not_guessed() -> None:
    assert normalize_currency("SYP") is None
