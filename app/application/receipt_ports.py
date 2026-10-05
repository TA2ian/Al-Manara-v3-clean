from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus


@dataclass(frozen=True, slots=True)
class ReceiptReservation:
    attempt: ReceiptAttempt
    replayed: bool


class ReceiptAttemptRepository(Protocol):
    async def reserve_next_attempt(
        self,
        order_id: UUID,
        telegram_user_id: int,
        idempotency_key: str,
        submitted_at: datetime,
        mime_type: str,
        telegram_file_id: str,
    ) -> ReceiptReservation: ...

    async def finalize(
        self,
        attempt_id: UUID,
        status: ReceiptAttemptStatus,
        failure_reason: str | None = None,
    ) -> ReceiptAttempt: ...


class ReceiptImageInspector(Protocol):
    async def inspect(self, telegram_file_id: str, declared_mime_type: str) -> None: ...


class ReceiptVerifier(Protocol):
    async def verify(self, attempt: ReceiptAttempt) -> ReceiptAttemptStatus: ...


class ReceiptEscalationPort(Protocol):
    async def escalate(self, order_id: UUID, attempt_id: UUID, reason: str) -> None: ...


class ReceiptClock(Protocol):
    def now(self) -> datetime: ...
