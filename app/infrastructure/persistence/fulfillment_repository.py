from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from app.application.fulfillment import FulfillmentRepository, FulfillmentResult


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class FulfillmentPersistenceError(RuntimeError):
    """Raised when a fulfillment RPC fails or returns an invalid payload."""


class SupabaseFulfillmentRepository(FulfillmentRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def claim(self, internal_order_id: UUID, expected_version: int, admin_telegram_user_id: int, actor_type: str, idempotency_key: str) -> FulfillmentResult:
        return await self._execute(
            "claim_order_fulfillment",
            {
                "p_order_id": str(internal_order_id),
                "p_expected_version": expected_version,
                "p_admin_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_idempotency_key": idempotency_key,
            },
            require_claimed=True,
        )

    async def complete(self, internal_order_id: UUID, expected_version: int, admin_telegram_user_id: int, actor_type: str, idempotency_key: str) -> FulfillmentResult:
        return await self._execute(
            "complete_order_fulfillment",
            {
                "p_order_id": str(internal_order_id),
                "p_expected_version": expected_version,
                "p_admin_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_idempotency_key": idempotency_key,
            },
            require_claimed=False,
        )

    async def _execute(self, function_name: str, params: dict[str, Any], require_claimed: bool) -> FulfillmentResult:
        try:
            response = await asyncio.to_thread(self._client.rpc(function_name, params).execute)
        except Exception as exc:
            raise FulfillmentPersistenceError(f"fulfillment persistence RPC failed: {function_name}") from exc
        error = getattr(response, "error", None)
        if error:
            raise FulfillmentPersistenceError(self._error_message(function_name, error))
        data = getattr(response, "data", None)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise FulfillmentPersistenceError(f"invalid fulfillment RPC response: {function_name}")
        row = data[0]
        try:
            occurred_key = "claimed_at" if require_claimed else "completed_at"
            occurred_at = row[occurred_key]
            if isinstance(occurred_at, str):
                occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
                raise ValueError("timestamp must be timezone-aware")
            return FulfillmentResult(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=str(row["status"]).strip().upper(),
                version=int(row["version"]),
                admin_telegram_user_id=int(row.get("admin_telegram_user_id", params["p_admin_telegram_user_id"])),
                occurred_at=occurred_at.astimezone(timezone.utc),
                replayed=bool(row.get("replayed", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FulfillmentPersistenceError(f"invalid fulfillment RPC payload: {function_name}") from exc

    @staticmethod
    def _error_message(function_name: str, error: Any) -> str:
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return f"{function_name} failed: {message.strip()}"
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return f"{function_name} failed: {value.strip()}"
        return f"{function_name} failed: {str(error).strip() or 'unknown persistence error'}"
