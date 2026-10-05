from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.customer_order_details import CustomerOrderDetails, CustomerOrderDetailsRepository
from app.domain.order_status import OrderStatus


class SupabaseCustomerOrderDetailsRepository(CustomerOrderDetailsRepository):
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_order(
        self, customer_telegram_user_id: int, public_order_code: str
    ) -> CustomerOrderDetails | None:
        # Get order basic details
        order_res = (
            self._client.table("orders")
            .select("id, status, version, created_at, network, public_code")
            .eq("customer_telegram_user_id", customer_telegram_user_id)
            .eq("public_code", public_order_code)
            .maybe_single()
            .execute()
        )
        order_data = order_res.data
        if not order_data:
            return None

        internal_order_id = UUID(order_data["id"])
        
        # Get financial snapshot
        snap_res = (
            self._client.table("order_financial_snapshots")
            .select("requested_amount, payment_currency, local_amount")
            .eq("order_id", str(internal_order_id))
            .maybe_single()
            .execute()
        )
        snap_data = snap_res.data or {}

        return CustomerOrderDetails(
            internal_order_id=internal_order_id,
            public_order_code=order_data["public_code"],
            status=OrderStatus(order_data["status"]),
            version=order_data["version"],
            network_code=order_data["network"],
            requested_amount=Decimal(str(snap_data["requested_amount"])) if snap_data.get("requested_amount") else None,
            payment_currency=snap_data.get("payment_currency"),
            local_amount=Decimal(str(snap_data["local_amount"])) if snap_data.get("local_amount") else None,
            created_at=order_data["created_at"],
        )
