from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class OcrField(StrEnum):
    AMOUNT = "amount"
    CURRENCY = "currency"
    REFERENCE = "reference"
    NETWORK = "network"


@dataclass(frozen=True, slots=True)
class OcrFieldValue:
    value: str
    confidence: Decimal

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("OCR field value cannot be empty")
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("OCR confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class OcrResult:
    receipt_id: UUID
    fields: dict[OcrField, OcrFieldValue]
    provider: str
    provider_version: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.provider_version.strip():
            raise ValueError("OCR provider metadata is required")


class OcrPort(Protocol):
    async def extract(self, image: bytes, mime_type: str, receipt_id: UUID) -> OcrResult: ...
