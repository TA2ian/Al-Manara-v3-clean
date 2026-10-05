from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

from app.domain.currency import CurrencyCode, normalize_currency
from app.domain.receipt_ocr import OcrField, OcrFieldValue, OcrResult


_AMOUNT_RE = re.compile(r"[^0-9,.-]")


def normalize_amount(raw: str) -> Decimal | None:
    cleaned = _AMOUNT_RE.sub("", raw.strip()).replace(",", "")
    if not cleaned or cleaned in {".", "-", "+"}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount > 0 else None


def normalize_currency_field(raw: str) -> CurrencyCode | None:
    return normalize_currency(raw)


def normalize_ocr_result(result: OcrResult) -> dict[OcrField, OcrFieldValue]:
    normalized: dict[OcrField, OcrFieldValue] = {}
    for field, field_value in result.fields.items():
        value = field_value.value.strip()
        if field is OcrField.AMOUNT:
            amount = normalize_amount(value)
            if amount is None:
                continue
            value = format(amount, "f")
        elif field is OcrField.CURRENCY:
            currency = normalize_currency_field(value)
            if currency is None:
                continue
            value = currency.value
        elif field in (OcrField.REFERENCE, OcrField.NETWORK):
            value = " ".join(value.split())
        if value:
            normalized[field] = OcrFieldValue(value, field_value.confidence)
    return normalized
