from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_order_listing import (
    AdminOrderListItem,
    AdminOrderListType,
    AdminOrderPage,
    AdminOrderListingRepository,
)


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminOrderListingPersistenceError(RuntimeError):
    pass


class SupabaseAdminOrderListingRepository(AdminOrderListingRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def list_orders(self, admin_telegram_user_id: int, actor_type: str, list_type: AdminOrderListType, page: int, page_size: int) -> AdminOrderPage:
        rpc_name = "list_admin_fulfillment_orders" if list_type is AdminOrderListType.FULFILLMENT else "list_admin_orders"
        params = {
            "p_admin_telegram_user_id": admin_telegram_user_id,
            "p_actor_type": actor_type,
            "p_page": page,
            "p_page_size": page_size,
        }
        if rpc_name == "list_admin_orders":
            params["p_list_type"] = list_type.value
        try:
            response = await asyncio.to_thread(self._client.rpc(rpc_name, params).execute)
        except Exception as exc:
            raise AdminOrderListingPersistenceError("admin order listing RPC failed") from exc
        error = getattr(response, "error", None)
        if error:
            raise AdminOrderListingPersistenceError("admin order listing RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminOrderListingPersistenceError("admin order listing RPC returned invalid data")
        items: list[AdminOrderListItem] = []
        total_count = 0
        for row in data:
            if not isinstance(row, dict):
                raise AdminOrderListingPersistenceError("admin order listing contains an invalid row")
            try:
                created_at = row["created_at"]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if not isinstance(created_at, datetime) or created_at.tzinfo is None:
                    raise ValueError("created_at must be timezone-aware")
                claim_owner = row.get("fulfillment_claimed_by")
                item = AdminOrderListItem(
                    internal_order_id=UUID(str(row["internal_order_id"])),
                    public_order_code=str(row["public_order_code"]),
                    user_telegram_id=int(row["user_telegram_id"]),
                    wallet_id=UUID(str(row["wallet_id"])),
                    network_code=str(row["network_code"]),
                    status=str(row["status"]),
                    version=int(row["version"]),
                    requested_amount=Decimal(str(row["requested_amount"])) if row.get("requested_amount") is not None else None,
                    payment_currency=str(row["payment_currency"]) if row.get("payment_currency") is not None else None,
                    local_amount=Decimal(str(row["local_amount"])) if row.get("local_amount") is not None else None,
                    created_at=created_at,
                    fulfillment_claimed_by=int(claim_owner) if claim_owner is not None else None,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise AdminOrderListingPersistenceError("invalid admin order listing payload") from exc
            items.append(item)
            total_count = max(total_count, int(row.get("total_count", 0)))
        return AdminOrderPage(tuple(items), page, page_size, total_count)
