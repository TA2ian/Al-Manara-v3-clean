from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReceiptVerificationPolicy:
    minimum_ocr_confidence: Decimal = Decimal("0.70")
    require_network: bool = False
    require_reference: bool = False
    allow_missing_network_as_suspicious: bool = True

    def __post_init__(self) -> None:
        if not self.minimum_ocr_confidence.is_finite() or not Decimal("0") <= self.minimum_ocr_confidence <= Decimal("1"):
            raise ValueError("minimum OCR confidence must be between 0 and 1")


DEFAULT_RECEIPT_VERIFICATION_POLICY = ReceiptVerificationPolicy()
