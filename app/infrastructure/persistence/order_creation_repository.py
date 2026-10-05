from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from app.application.order_creation_ports import PersistedOrderCreation
from app.domain.order_draft import PurchaseOrderDraft
from app.domain.order_status import OrderStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class OrderCreationPersistenceError(RuntimeError):
    """Raised when the atomic order-creation RPC cannot be completed safely."""


class SupabaseOrderCreationRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def create_order_atomically(self, draft: PurchaseOrderDraft) -> PersistedOrderCreation:
        financials = draft.financials
        params = {
            "p_internal_order_id": str(draft.internal_order_id),
            "p_public_order_code": draft.public_order_code.strip(),
            "p_user_id": draft.user_id,
            "p_wallet_id": str(draft.wallet_id),
            "p_network_code": draft.network.value,
            "p_wallet_address": draft.wallet_address,
            "p_requested_amount": str(financials.requested_amount),
            "p_fee_percent": str(financials.fee_percent),
            "p_fee_amount": str(financials.fee_amount),
            "p_net_usdt_amount": str(financials.net_usdt_amount),
            "p_payment_currency": financials.payment_currency,
            "p_exchange_rate": (
                str(financials.exchange_rate) if financials.exchange_rate is not None else None
            ),
            "p_local_amount": str(financials.local_amount),
            "p_rounding_policy_version": financials.rounding_policy_version,
            "p_customer_verified_name_snapshot": draft.customer_payment_identity.verified_name,
            "p_customer_shamcash_account_snapshot": draft.customer_payment_identity.verified_shamcash_account,
            "p_admin_payment_account_name_snapshot": draft.admin_payment_account.account_name,
            "p_admin_payment_account_number_snapshot": draft.admin_payment_account.account_number,
            "p_admin_payment_qr_file_id_snapshot": draft.admin_payment_account.qr_image_file_id,
            "p_quote_issued_at": draft.quote_issued_at.isoformat(),
            "p_quote_expires_at": draft.quote_expires_at.isoformat(),
            "p_idempotency_key": draft.idempotency_key.strip(),
        }

        try:
            query = self._client.rpc("create_purchase_order_atomic", params)
            response = await asyncio.to_thread(query.execute)
        except Exception as exc:
            raise OrderCreationPersistenceError("order creation RPC failed") from exc

        error = getattr(response, "error", None)
        if error:
            raise OrderCreationPersistenceError(self._error_message(error))

        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise OrderCreationPersistenceError("order creation RPC returned an invalid payload")

        row = data[0]
        try:
            return PersistedOrderCreation(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=OrderStatus(str(row["status"])),
                version=int(row["version"]),
                replayed=self._parse_bool(row["replayed"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrderCreationPersistenceError("invalid order creation RPC payload") from exc

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ValueError("invalid replayed value")

    @staticmethod
    def _error_message(error: Any) -> str:
        if isinstance(error, str):
            return error.strip()
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(error).strip() or "unknown persistence error"
