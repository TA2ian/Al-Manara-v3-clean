from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_order_closure import (
    AdminOrderClosureRepository,
    AdminOrderClosureResult,
)


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminOrderClosurePersistenceError(RuntimeError):
    """Raised when the administrative closure RPC fails or is malformed."""


class SupabaseAdminOrderClosureRepository(AdminOrderClosureRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def close_without_fulfillment(
        self,
        internal_order_id: UUID,
        expected_version: int,
        admin_telegram_user_id: int,
        session_id: UUID,
        reason: str,
        idempotency_key: str,
    ) -> AdminOrderClosureResult:
        try:
            response = await asyncio.to_thread(
                self._client.rpc(
                    "close_order_without_fulfillment",
                    {
                        "p_order_id": str(internal_order_id),
                        "p_expected_version": expected_version,
                        "p_admin_telegram_user_id": admin_telegram_user_id,
                        "p_session_id": str(session_id),
                        "p_reason": reason,
                        "p_idempotency_key": idempotency_key,
                    },
                ).execute
            )
        except Exception as exc:
            raise AdminOrderClosurePersistenceError(
                "administrative closure RPC failed"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            raise AdminOrderClosurePersistenceError(self._error_message(error))

        data = getattr(response, "data", None)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise AdminOrderClosurePersistenceError("invalid administrative closure response")

        row = data[0]
        try:
            return AdminOrderClosureResult(
                internal_order_id=UUID(str(row["internal_order_id"])),
                public_order_code=str(row["public_order_code"]),
                status=str(row["status"]).strip().upper(),
                version=int(row["version"]),
                replayed=bool(row.get("replayed", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminOrderClosurePersistenceError(
                "invalid administrative closure payload"
            ) from exc

    @staticmethod
    def _error_message(error: Any) -> str:
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return f"administrative closure failed: {message.strip()}"
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return f"administrative closure failed: {value.strip()}"
        return "administrative closure failed"
