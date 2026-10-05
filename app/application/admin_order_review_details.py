from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AdminReceiptView:
    submission_id: UUID
    attempt_number: int
    input_type: str
    processing_status: str
    linkage_status: str
    telegram_file_id: str | None
    mime_type: str | None
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class AdminOrderReviewDetails:
    internal_order_id: UUID
    public_order_code: str
    status: str
    version: int
    user_telegram_id: int
    network_code: str
    requested_amount: Decimal | None
    payment_currency: str | None
    local_amount: Decimal | None
    latest_receipt: AdminReceiptView | None


@dataclass(frozen=True, slots=True)
class GetAdminOrderReviewDetailsCommand:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    session_id: UUID | None = None


class AdminOrderReviewDetailsRepository(Protocol):
    async def get_details(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        order_id: UUID,
    ) -> AdminOrderReviewDetails: ...


class AdminOrderReviewDetailsService:
    def __init__(self, repository: AdminOrderReviewDetailsRepository) -> None:
        self._repository = repository

    async def get(self, command: GetAdminOrderReviewDetailsCommand) -> AdminOrderReviewDetails:
        if not isinstance(command.admin_user_id, int) or command.admin_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        if command.actor_type not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        if not isinstance(command.order_id, UUID):
            raise ValueError("order id is required")
        return await self._repository.get_details(
            command.admin_user_id,
            command.actor_type,
            command.order_id,
        )
