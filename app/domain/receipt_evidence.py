from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.receipt_verification import VerificationDecision


class EvidenceMatch(StrEnum):
    MATCHED = "matched"
    MISMATCHED = "mismatched"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    amount: EvidenceMatch
    currency: EvidenceMatch
    network: EvidenceMatch
    reference: EvidenceMatch
    ocr_confidence: Decimal
    tolerance_used: Decimal
    reasons: tuple[str, ...]
    decision: VerificationDecision

    def __post_init__(self) -> None:
        if not self.ocr_confidence.is_finite() or not Decimal("0") <= self.ocr_confidence <= Decimal("1"):
            raise ValueError("invalid OCR confidence")
        if not self.tolerance_used.is_finite() or self.tolerance_used < 0:
            raise ValueError("invalid verification tolerance")
