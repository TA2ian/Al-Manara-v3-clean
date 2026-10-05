from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.receipt_ports import (
    ReceiptAttemptRepository,
    ReceiptClock,
    ReceiptEscalationPort,
    ReceiptImageInspector,
    ReceiptVerifier,
)
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, SUPPORTED_RECEIPT_MIME_TYPES


@dataclass(frozen=True, slots=True)
class SubmitReceiptCommand:
    order_id: UUID
    telegram_user_id: int
    telegram_file_id: str
    mime_type: str
    idempotency_key: str


class SubmitReceiptService:
    def __init__(
        self,
        attempts: ReceiptAttemptRepository,
        inspector: ReceiptImageInspector,
        verifier: ReceiptVerifier,
        escalation: ReceiptEscalationPort,
        clock: ReceiptClock,
    ) -> None:
        self._attempts = attempts
        self._inspector = inspector
        self._verifier = verifier
        self._escalation = escalation
        self._clock = clock

    async def submit(self, command: SubmitReceiptCommand):
        if command.telegram_user_id <= 0:
            raise ValueError("telegram user id must be positive")

        if command.mime_type not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt image type; JPEG, PNG, or WEBP is required")

        telegram_file_id = command.telegram_file_id.strip()
        if not telegram_file_id:
            raise ValueError("receipt file id is required")

        idempotency_key = command.idempotency_key.strip()
        if not idempotency_key:
            raise ValueError("idempotency key is required")

        submitted_at = self._clock.now()
        if submitted_at.tzinfo is None:
            raise RuntimeError("receipt clock must return a timezone-aware datetime")

        reservation = await self._attempts.reserve_next_attempt(
            order_id=command.order_id,
            telegram_user_id=command.telegram_user_id,
            idempotency_key=idempotency_key,
            submitted_at=submitted_at,
            mime_type=command.mime_type,
            telegram_file_id=telegram_file_id,
        )
        attempt = reservation.attempt

        if reservation.replayed:
            return attempt

        try:
            await self._inspector.inspect(telegram_file_id, command.mime_type)
            verification_status = await self._verifier.verify(attempt)
        except Exception as exc:
            reason = str(exc).strip() or "receipt processing failed"
            finalized = await self._finalize_failure(attempt, reason)
            if attempt.attempt_number == 3:
                await self._escalation.escalate(command.order_id, finalized.attempt_id, reason)
            raise

        if verification_status is ReceiptAttemptStatus.VERIFIED:
            return await self._attempts.finalize(
                attempt.attempt_id,
                ReceiptAttemptStatus.VERIFIED,
            )

        reason = "receipt could not be verified"
        finalized = await self._finalize_failure(attempt, reason)
        if attempt.attempt_number == 3:
            await self._escalation.escalate(command.order_id, finalized.attempt_id, reason)
        raise ValueError(reason)

    async def _finalize_failure(self, attempt: ReceiptAttempt, reason: str) -> ReceiptAttempt:
        status = (
            ReceiptAttemptStatus.ESCALATED
            if attempt.attempt_number == 3
            else ReceiptAttemptStatus.FAILED
        )
        return await self._attempts.finalize(attempt.attempt_id, status, reason)
