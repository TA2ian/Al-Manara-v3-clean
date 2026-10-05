from decimal import Decimal
from uuid import uuid4

from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_engine import verify_receipt


def context(currency: str = "USD", amount: str = "100.00") -> ReceiptVerificationContext:
    return ReceiptVerificationContext(
        order_id=uuid4(),
        payment_currency=currency,
        expected_payment_amount=Decimal(amount),
        exchange_rate=None if currency == "USD" else Decimal("100.00"),
        fee_percent=Decimal("1.00"),
        rounding_policy_version="v1",
        network_code="TRC20",
        wallet_address="T9yD14Nj9j7xAB4dbGeiX9h8unkM4Jx7nQ",
    )


def extracted(
    amount: str | None = "100.00",
    currency: str | None = "USD",
    confidence: str = "0.95",
) -> ExtractedReceiptData:
    return ExtractedReceiptData(
        uuid4(),
        Decimal(amount) if amount else None,
        currency,
        None,
        "TRC20",
        Decimal(confidence),
    )


def test_verified_when_currency_amount_and_confidence_are_valid() -> None:
    result = verify_receipt(context(), extracted())
    assert result.decision is VerificationDecision.VERIFIED


def test_mismatch_when_currency_is_wrong() -> None:
    result = verify_receipt(context(), extracted(currency="NEW.SYP"))
    assert result.decision is VerificationDecision.MISMATCH
    assert "currency_mismatch" in result.reasons


def test_verified_when_new_syp_alias_matches_new_syp_context() -> None:
    result = verify_receipt(
        context(currency="NEW.SYP", amount="10000.00"),
        extracted(amount="10000.00", currency="NEW SYRIAN POUND"),
    )
    assert result.decision is VerificationDecision.VERIFIED


def test_verified_when_arabic_new_syp_alias_matches_new_syp_context() -> None:
    result = verify_receipt(
        context(currency="NEW.SYP", amount="10000.00"),
        extracted(amount="10000.00", currency="ليرة جديدة سورية"),
    )
    assert result.decision is VerificationDecision.VERIFIED


def test_insufficient_data_when_amount_is_missing() -> None:
    result = verify_receipt(context(), extracted(amount=None))
    assert result.decision is VerificationDecision.INSUFFICIENT_DATA


def test_suspicious_when_ocr_confidence_is_low_but_financial_match_is_exact() -> None:
    result = verify_receipt(context(), extracted(confidence="0.69"))
    assert result.decision is VerificationDecision.SUSPICIOUS


def test_mismatch_when_amount_exceeds_tolerance() -> None:
    result = verify_receipt(context(), extracted(amount="100.05"))
    assert result.decision is VerificationDecision.MISMATCH
