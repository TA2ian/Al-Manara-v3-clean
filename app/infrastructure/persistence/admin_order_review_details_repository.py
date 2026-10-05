from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.admin_order_review_details import (
    AdminOrderReviewDetails,
    AdminOrderReviewDetailsRepository,
    AdminReceiptView,
)


class SupabaseAdminOrderReviewDetailsRepository(AdminOrderReviewDetailsRepository):
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_details(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        order_id: UUID,
    ) -> AdminOrderReviewDetails:
        # 1. Fetch order basics
        order_res = (
            self._client.table("orders")
            .select("id, status, version, customer_telegram_user_id, network, public_code")
            .eq("id", str(order_id))
            .maybe_single()
            .execute()
        )
        order_data = order_res.data
        if not order_data:
            raise ValueError("Order not found")

        # 2. Fetch financial snapshot
        snap_res = (
            self._client.table("order_financial_snapshots")
            .select("requested_amount, payment_currency, local_amount")
            .eq("order_id", str(order_id))
            .maybe_single()
            .execute()
        )
        snap_data = snap_res.data or {}

        # 3. Fetch latest receipt submission
        receipt_res = (
            self._client.table("receipt_submissions")
            .select("id, attempt_number, input_type, status, mime_type, telegram_file_id, created_at")
            .eq("order_id", str(order_id))
            .order("attempt_number", desc=True)
            .limit(1)
            .execute()
        )
        
        latest_receipt = None
        if receipt_res.data and len(receipt_res.data) > 0:
            rec = receipt_res.data[0]
            latest_receipt = AdminReceiptView(
                submission_id=UUID(rec["id"]),
                attempt_number=rec["attempt_number"],
                input_type=rec["input_type"],
                processing_status=rec["status"],
                linkage_status="LINKED",
                telegram_file_id=rec.get("telegram_file_id"),
                mime_type=rec.get("mime_type"),
                submitted_at=rec["created_at"],
            )

        return AdminOrderReviewDetails(
            internal_order_id=UUID(order_data["id"]),
            public_order_code=order_data["public_code"],
            status=order_data["status"],
            version=order_data["version"],
            user_telegram_id=order_data["customer_telegram_user_id"],
            network_code=order_data["network"],
            requested_amount=Decimal(str(snap_data["requested_amount"])) if snap_data.get("requested_amount") else None,
            payment_currency=snap_data.get("payment_currency"),
            local_amount=Decimal(str(snap_data["local_amount"])) if snap_data.get("local_amount") else None,
            latest_receipt=latest_receipt,
        )
