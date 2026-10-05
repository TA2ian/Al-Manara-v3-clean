from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID


class SupabaseAdminSuperToolsRepository:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def reset_order_status(
        self,
        admin_user_id: int,
        internal_order_id: UUID,
        target_status: str = "UNDER_REVIEW",
        reason: str = "Reopened by admin",
    ) -> bool:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "admin_reset_order_status",
                    {
                        "p_admin_user_id": admin_user_id,
                        "p_internal_order_id": str(internal_order_id),
                        "p_target_status": target_status,
                        "p_reason": reason,
                    },
                ).execute
            )
            return bool(getattr(response, "data", None))
        except Exception as exc:
            raise RuntimeError("failed to reset order status") from exc

    async def edit_order_details(
        self,
        admin_user_id: int,
        internal_order_id: UUID,
        new_amount: Decimal | None = None,
        new_currency: str | None = None,
        new_network: str | None = None,
    ) -> bool:
        try:
            params: dict[str, Any] = {
                "p_admin_user_id": admin_user_id,
                "p_internal_order_id": str(internal_order_id),
            }
            if new_amount is not None:
                params["p_new_amount"] = float(new_amount)
            if new_currency is not None:
                params["p_new_currency"] = new_currency
            if new_network is not None:
                params["p_new_network"] = new_network

            response = await asyncio.to_thread(
                self._client.rpc("admin_edit_order_details", params).execute
            )
            return bool(getattr(response, "data", None))
        except Exception as exc:
            raise RuntimeError("failed to edit order details") from exc

    async def delete_order(
        self,
        admin_user_id: int,
        internal_order_id: UUID,
    ) -> bool:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "admin_delete_order",
                    {
                        "p_admin_user_id": admin_user_id,
                        "p_internal_order_id": str(internal_order_id),
                    },
                ).execute
            )
            return bool(getattr(response, "data", False))
        except Exception as exc:
            raise RuntimeError("failed to delete order") from exc

    async def get_order_id_by_code(self, public_order_code: str) -> UUID | None:
        try:
            response = await asyncio.to_thread(
                self._client.table("purchase_orders")
                .select("id")
                .eq("public_order_code", public_order_code.strip())
                .execute
            )
            data = getattr(response, "data", [])
            if data and "id" in data[0]:
                return UUID(data[0]["id"])
            return None
        except Exception:
            return None
