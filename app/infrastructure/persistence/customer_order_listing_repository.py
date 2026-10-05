from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.application.customer_order_listing import (
    CustomerOrderListItem,
    CustomerOrderListingRepository,
    CustomerOrderPage,
)
from app.domain.order_status import OrderStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class CustomerOrderListingPersistenceError(RuntimeError):
    """Raised when the customer-safe listing RPC returns an invalid result."""


class SupabaseCustomerOrderListingRepository(CustomerOrderListingRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def list_orders(
        self, customer_telegram_user_id: int, page: int, page_size: int
    ) -> CustomerOrderPage:
        total_count = await self._count_orders(customer_telegram_user_id)
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "list_customer_orders",
                    {
                        "p_telegram_user_id": customer_telegram_user_id,
                        "p_page": page,
                        "p_page_size": page_size,
                    },
                ).execute
            )
        except Exception as exc:
            raise CustomerOrderListingPersistenceError(
                "customer order listing RPC failed"
            ) from exc
        if getattr(response, "error", None):
            raise CustomerOrderListingPersistenceError(
                "customer order listing RPC returned an error"
            )
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise CustomerOrderListingPersistenceError(
                "customer order listing RPC returned invalid data"
            )

        items: list[CustomerOrderListItem] = []
        for row in data:
            if not isinstance(row, dict):
                raise CustomerOrderListingPersistenceError(
                    "customer order listing contains an invalid row"
                )
            try:
                created_at = row["created_at"]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                if not isinstance(created_at, datetime) or created_at.tzinfo is None:
                    raise ValueError("created_at must be timezone-aware")
                item = CustomerOrderListItem(
                    public_order_code=str(row["public_order_code"]),
                    status=OrderStatus(str(row["status"]).strip().upper()),
                    version=int(row["version"]),
                    network_code=str(row["network_code"]),
                    requested_amount=(
                        Decimal(str(row["requested_amount"]))
                        if row.get("requested_amount") is not None
                        else None
                    ),
                    payment_currency=(
                        str(row["payment_currency"])
                        if row.get("payment_currency") is not None
                        else None
                    ),
                    local_amount=(
                        Decimal(str(row["local_amount"]))
                        if row.get("local_amount") is not None
                        else None
                    ),
                    created_at=created_at,
                )
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise CustomerOrderListingPersistenceError(
                    "invalid customer order listing payload"
                ) from exc
            items.append(item)
        return CustomerOrderPage(tuple(items), page, page_size, total_count)

    async def _count_orders(self, customer_telegram_user_id: int) -> int:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "count_customer_orders",
                    {"p_telegram_user_id": customer_telegram_user_id},
                ).execute
            )
        except Exception as exc:
            raise CustomerOrderListingPersistenceError(
                "customer order count RPC failed"
            ) from exc
        if getattr(response, "error", None):
            raise CustomerOrderListingPersistenceError(
                "customer order count RPC returned an error"
            )
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise CustomerOrderListingPersistenceError(
                "customer order count RPC returned invalid data"
            )
        try:
            total_count = int(data[0]["total_count"])
            if total_count < 0:
                raise ValueError("total_count must be non-negative")
        except (KeyError, TypeError, ValueError) as exc:
            raise CustomerOrderListingPersistenceError(
                "invalid customer order count payload"
            ) from exc
        return total_count