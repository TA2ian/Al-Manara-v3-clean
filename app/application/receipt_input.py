from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReceiptInputDecision(StrEnum):
    PROCESS_IMAGE = "process_image"
    GUIDE_USER = "guide_user"


PDF_MIME_TYPE = "application/pdf"
SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(frozen=True, slots=True)
class ReceiptInputResult:
    decision: ReceiptInputDecision
    user_message_key: str | None = None


def classify_receipt_input(*, mime_type: str | None, filename: str | None) -> ReceiptInputResult:
    normalized_mime = (mime_type or "").strip().lower()
    normalized_filename = (filename or "").strip().lower()

    if normalized_mime == PDF_MIME_TYPE or normalized_filename.endswith(".pdf"):
        return ReceiptInputResult(
            decision=ReceiptInputDecision.GUIDE_USER,
            user_message_key="receipt.pdf_guidance",
        )

    if normalized_mime in SUPPORTED_IMAGE_MIME_TYPES:
        return ReceiptInputResult(decision=ReceiptInputDecision.PROCESS_IMAGE)

    return ReceiptInputResult(
        decision=ReceiptInputDecision.GUIDE_USER,
        user_message_key="receipt.unsupported_format",
    )
