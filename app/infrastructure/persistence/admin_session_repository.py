from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.admin_session import AdminSession, AdminSessionRepository


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class AdminSessionPersistenceError(RuntimeError):
    pass


class SupabaseAdminSessionRepository(AdminSessionRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def create(self, admin_telegram_user_id: int, actor_type: str) -> AdminSession:
        response = await self._call("create_admin_session", {
            "p_admin_telegram_user_id": admin_telegram_user_id,
            "p_actor_type": actor_type,
        })
        if len(response) != 1 or not isinstance(response[0], dict):
            raise AdminSessionPersistenceError("admin session creation returned invalid data")
        try:
            expires_at = response[0]["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
                raise ValueError("invalid expiry")
            return AdminSession(UUID(str(response[0]["session_id"])), expires_at)
        except (KeyError, TypeError, ValueError) as exc:
            raise AdminSessionPersistenceError("invalid admin session payload") from exc

    async def revoke(self, admin_telegram_user_id: int, actor_type: str, session_id: UUID) -> bool:
        response = await self._call("revoke_admin_session", {
            "p_admin_telegram_user_id": admin_telegram_user_id,
            "p_actor_type": actor_type,
            "p_session_id": str(session_id),
        })
        if len(response) != 1 or not isinstance(response[0], dict):
            raise AdminSessionPersistenceError("admin session revocation returned invalid data")
        value = response[0].get("revoke_admin_session")
        if not isinstance(value, bool):
            raise AdminSessionPersistenceError("admin session revocation returned invalid result")
        return value

    async def _call(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(self._client.rpc(function_name, params).execute)
        except Exception as exc:
            raise AdminSessionPersistenceError("admin session RPC failed") from exc
        if getattr(response, "error", None):
            raise AdminSessionPersistenceError("admin session RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise AdminSessionPersistenceError("admin session RPC returned invalid data")
        return [dict(row) for row in data if isinstance(row, dict)]
