from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.order_status import OrderStatus


@dataclass(frozen=True, slots=True)
class CustomerOrderDetails:
    internal_order_id: UUID
    public_order_code: str
    status: OrderStatus
    version: int
    network_code: str
    requested_amount: Decimal | None
    payment_currency: str | None
    local_amount: Decimal | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GetCustomerOrderDetailsCommand:
    customer_telegram_user_id: int
    public_order_code: str


class CustomerOrderDetailsRepository(Protocol):
    async def get_order(
        self, customer_telegram_user_id: int, public_order_code: str
    ) -> CustomerOrderDetails | None: ...


class CustomerOrderDetailsService:
    """Service to retrieve details of a specific order for a customer."""

    def __init__(self, repository: CustomerOrderDetailsRepository) -> None:
        self._repository = repository

    async def get(self, command: GetCustomerOrderDetailsCommand) -> CustomerOrderDetails | None:
        if not isinstance(command.customer_telegram_user_id, int) or command.customer_telegram_user_id <= 0:
            raise ValueError("customer identity must be positive")
        code = command.public_order_code.strip()
        if not code or len(code) > 100:
            raise ValueError("order code is invalid")
        return await self._repository.get_order(command.customer_telegram_user_id, code)
