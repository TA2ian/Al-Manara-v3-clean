from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol
from uuid import UUID


class AdminOrderListType(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REVIEW = "review"
    FULFILLMENT = "fulfillment"


@dataclass(frozen=True, slots=True)
class AdminOrderListItem:
    internal_order_id: UUID
    public_order_code: str
    user_telegram_id: int
    wallet_id: UUID
    network_code: str
    status: str
    version: int
    requested_amount: Decimal | None
    payment_currency: str | None
    local_amount: Decimal | None
    created_at: datetime
    fulfillment_claimed_by: int | None = None


@dataclass(frozen=True, slots=True)
class AdminOrderPage:
    items: tuple[AdminOrderListItem, ...]
    page: int
    page_size: int
    total_count: int


@dataclass(frozen=True, slots=True)
class ListAdminOrdersCommand:
    admin_telegram_user_id: int
    actor_type: str
    list_type: AdminOrderListType | str = AdminOrderListType.ACTIVE
    page: int = 0
    page_size: int = 5


class AdminOrderListingRepository(Protocol):
    async def list_orders(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        list_type: AdminOrderListType,
        page: int,
        page_size: int,
    ) -> AdminOrderPage: ...


class AdminOrderListingService:
    def __init__(self, repository: AdminOrderListingRepository) -> None:
        self._repository = repository

    async def list(self, command: ListAdminOrdersCommand) -> AdminOrderPage:
        if not isinstance(command.admin_telegram_user_id, int) or command.admin_telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        if not isinstance(command.actor_type, str):
            raise ValueError("administrator actor type is required")
        actor_type = command.actor_type.strip().lower()
        if actor_type not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        try:
            list_type = command.list_type if isinstance(command.list_type, AdminOrderListType) else AdminOrderListType(command.list_type.strip().lower())
        except (AttributeError, ValueError) as exc:
            raise ValueError("invalid order list type") from exc
        if not isinstance(command.page, int) or command.page < 0:
            raise ValueError("page must be non-negative")
        if not isinstance(command.page_size, int) or command.page_size < 1 or command.page_size > 50:
            raise ValueError("page size must be between 1 and 50")
        return await self._repository.list_orders(
            command.admin_telegram_user_id, actor_type, list_type, command.page, command.page_size
        )
