from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReceiptAttemptStatus(StrEnum):
    PROCESSING = "processing"
    FAILED = "failed"
    VERIFIED = "verified"
    ESCALATED = "escalated"


SUPPORTED_RECEIPT_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_RECEIPT_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ReceiptAttempt:
    attempt_id: UUID
    order_id: UUID
    attempt_number: int
    mime_type: str
    telegram_file_id: str
    submitted_at: datetime
    status: ReceiptAttemptStatus
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.attempt_number <= MAX_RECEIPT_ATTEMPTS:
            raise ValueError("receipt attempt number must be between 1 and 3")
        if self.mime_type not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt MIME type")
        if not self.telegram_file_id.strip():
            raise ValueError("telegram file id is required")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        if self.status in (ReceiptAttemptStatus.FAILED, ReceiptAttemptStatus.ESCALATED):
            if not (self.failure_reason or "").strip():
                raise ValueError("failed or escalated receipt attempts require a failure reason")
        elif self.failure_reason is not None:
            raise ValueError("failure reason is only valid for failed or escalated attempts")
