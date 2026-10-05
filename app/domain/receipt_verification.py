from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


ABSOLUTE_TOLERANCE = Decimal("0.04")


class VerificationDecision(StrEnum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    INSUFFICIENT_DATA = "insufficient_data"
    UNREADABLE = "unreadable"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True, slots=True)
class ExtractedReceiptData:
    receipt_id: UUID
    amount: Decimal | None
    currency: str | None
    reference: str | None
    network: str | None
    confidence: Decimal

    def __post_init__(self) -> None:
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("receipt confidence must be between 0 and 1")
        if self.amount is not None and (not self.amount.is_finite() or self.amount <= 0):
            raise ValueError("receipt amount must be positive and finite")


@dataclass(frozen=True, slots=True)
class FinancialMatchResult:
    decision: VerificationDecision
    expected_amount: Decimal
    extracted_amount: Decimal | None
    absolute_difference: Decimal | None


def match_receipt_amount(expected_amount: Decimal, extracted: ExtractedReceiptData, tolerance: Decimal = ABSOLUTE_TOLERANCE) -> FinancialMatchResult:
    if not expected_amount.is_finite() or expected_amount <= 0:
        raise ValueError("expected amount must be positive and finite")
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("tolerance must be finite and non-negative")
    if extracted.amount is None or extracted.currency is None:
        return FinancialMatchResult(VerificationDecision.INSUFFICIENT_DATA, expected_amount, extracted.amount, None)
    difference = abs(expected_amount - extracted.amount)
    decision = VerificationDecision.VERIFIED if difference <= tolerance else VerificationDecision.MISMATCH
    return FinancialMatchResult(decision, expected_amount, extracted.amount, difference)
