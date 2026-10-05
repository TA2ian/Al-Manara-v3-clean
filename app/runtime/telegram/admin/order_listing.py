"""Admin order listing Telegram handler."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import Router

from app.runtime.telegram.shared import messages as msg

ADMIN_ORDER_PAGE_SIZE = 5


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderListingInput:
    admin_user_id: int
    actor_type: str
    list_type: str  # active | review | fulfillment
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderListingResponse:
    ok: bool
    message: str
    page: Any | None = None


class TelegramAdminOrderListingHandler:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def handle(self, data: TelegramAdminOrderListingInput) -> TelegramAdminOrderListingResponse:
        if data.admin_user_id <= 0:
            return TelegramAdminOrderListingResponse(False, msg.ADMIN_IDENTITY_CHECK_FAILED)
        try:
            result = await self._service.list_orders(
                admin_telegram_user_id=data.admin_user_id,
                actor_type=data.actor_type,
                list_type=data.list_type,
                page=data.page,
                page_size=data.page_size,
            )
            return TelegramAdminOrderListingResponse(True, "", result)
        except (PermissionError, LookupError):
            return TelegramAdminOrderListingResponse(False, msg.ADMIN_UNAUTHORIZED)
        except Exception:
            return TelegramAdminOrderListingResponse(False, msg.ADMIN_ORDERS_LOAD_FAILED)


def build_admin_order_listing_router() -> Router:
    """Listing router is thin — actual display happens inside admin_dashboard."""
    return Router(name="admin-order-listing")
