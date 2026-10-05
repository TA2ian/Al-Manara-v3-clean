from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.order_status import OrderStatus


@dataclass(frozen=True, slots=True)
class CustomerOrderListItem:
    """A customer-safe order summary that deliberately omits internal identifiers."""

    public_order_code: str
    status: OrderStatus
    version: int
    network_code: str
    requested_amount: Decimal | None
    payment_currency: str | None
    local_amount: Decimal | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerOrderPage:
    items: tuple[CustomerOrderListItem, ...]
    page: int
    page_size: int
    total_count: int


@dataclass(frozen=True, slots=True)
class ListCustomerOrdersCommand:
    customer_telegram_user_id: int
    page: int = 0
    page_size: int = 5


class CustomerOrderListingRepository(Protocol):
    async def list_orders(
        self, customer_telegram_user_id: int, page: int, page_size: int
    ) -> CustomerOrderPage: ...


class CustomerOrderListingService:
    def __init__(self, repository: CustomerOrderListingRepository) -> None:
        self._repository = repository

    async def list(self, command: ListCustomerOrdersCommand) -> CustomerOrderPage:
        if (
            not isinstance(command.customer_telegram_user_id, int)
            or command.customer_telegram_user_id <= 0
        ):
            raise ValueError("customer identity must be positive")
        if not isinstance(command.page, int) or command.page < 0:
            raise ValueError("page must be non-negative")
        if (
            not isinstance(command.page_size, int)
            or command.page_size < 1
            or command.page_size > 50
        ):
            raise ValueError("page size must be between 1 and 50")
        return await self._repository.list_orders(
            command.customer_telegram_user_id, command.page, command.page_size
        )