from decimal import Decimal
from uuid import uuid4

from app.domain.receipt_verification import (
    ABSOLUTE_TOLERANCE,
    ExtractedReceiptData,
    VerificationDecision,
    match_receipt_amount,
)


def receipt(amount: str | None, currency: str | None = "USD") -> ExtractedReceiptData:
    return ExtractedReceiptData(uuid4(), Decimal(amount) if amount is not None else None, currency, None, None, Decimal("0.95"))


def test_amount_inside_absolute_tolerance_is_verified() -> None:
    result = match_receipt_amount(Decimal("100.00"), receipt("100.04"))
    assert result.decision is VerificationDecision.VERIFIED
    assert result.absolute_difference == ABSOLUTE_TOLERANCE


def test_amount_outside_absolute_tolerance_is_mismatch() -> None:
    result = match_receipt_amount(Decimal("100.00"), receipt("100.05"))
    assert result.decision is VerificationDecision.MISMATCH
    assert result.absolute_difference == Decimal("0.05")


def test_missing_amount_is_insufficient_data() -> None:
    result = match_receipt_amount(Decimal("100.00"), receipt(None))
    assert result.decision is VerificationDecision.INSUFFICIENT_DATA


def test_amount_matching_is_currency_agnostic() -> None:
    result = match_receipt_amount(Decimal("100.00"), receipt("100.00", "NEW.SYP"))
    assert result.decision is VerificationDecision.VERIFIED
