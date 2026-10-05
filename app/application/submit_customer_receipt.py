from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from typing import Awaitable, Callable

from app.application.receipt_image import ReceiptImageInspectorImpl
from app.application.receipt_orchestrator import ReceiptSubmission, ReceiptSubmissionOrchestrator
from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptClock
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, SUPPORTED_RECEIPT_MIME_TYPES


@dataclass(frozen=True, slots=True)
class SubmitCustomerReceiptCommand:
    order_id: UUID
    telegram_user_id: int
    telegram_file_id: str
    declared_mime_type: str
    idempotency_key: str


ProgressCallback = Callable[[int, str], Awaitable[None]]


class SubmitCustomerReceiptService:
    """Validates a Telegram image, reserves it, then queues it for human review.

    This boundary deliberately does not perform financial approval or infer payment
    validity. The database moves the order to UNDER_REVIEW only after the image has
    passed strict content validation and the receipt attempt has been reserved.
    """

    def __init__(
        self,
        attempts: ReceiptAttemptRepository,
        inspector: ReceiptImageInspectorImpl,
        clock: ReceiptClock,
        orchestrator: ReceiptSubmissionOrchestrator | None = None,
    ) -> None:
        self._attempts = attempts
        self._inspector = inspector
        self._clock = clock
        self._orchestrator = orchestrator

    async def submit(self, command: SubmitCustomerReceiptCommand, image_bytes: bytes = b"", progress: ProgressCallback | None = None) -> ReceiptAttempt:
        if not isinstance(command.order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.telegram_user_id, int) or command.telegram_user_id <= 0:
            raise ValueError("telegram user id must be positive")
        file_id = command.telegram_file_id.strip()
        if not file_id:
            raise ValueError("telegram file id is required")
        mime = command.declared_mime_type.strip().lower()
        if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt image type")
        key = command.idempotency_key.strip()
        if not key:
            raise ValueError("idempotency key is required")
        submitted_at = self._clock.now()
        if submitted_at.tzinfo is None:
            raise RuntimeError("receipt clock must return a timezone-aware datetime")

        reservation = await self._attempts.reserve_next_attempt(
            order_id=command.order_id,
            telegram_user_id=command.telegram_user_id,
            idempotency_key=key,
            submitted_at=submitted_at,
            mime_type=mime,
            telegram_file_id=file_id,
        )
        if reservation.replayed:
            return reservation.attempt
            
        if self._orchestrator is None:
            return reservation.attempt
            
        return await self._orchestrator.process(
            ReceiptSubmission(
                order_id=reservation.attempt.order_id,
                attempt_id=reservation.attempt.attempt_id,
                telegram_file_id=file_id,
                mime_type=reservation.attempt.mime_type or mime,
            ),
            image_bytes
        )
