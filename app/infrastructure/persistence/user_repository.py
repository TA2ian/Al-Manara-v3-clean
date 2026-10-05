from typing import Any, Protocol

class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...

class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...
    @property
    def table(self, table_name: str) -> Any: ...


class SupabaseUserRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def record_misconduct(self, telegram_user_id: int) -> None:
        try:
            # We must use a thread for sync client execute if it's sync
            import asyncio
            await asyncio.to_thread(
                self._client.rpc("record_user_misconduct", {"target_telegram_user_id": telegram_user_id}).execute
            )
        except Exception as exc:
            raise RuntimeError("failed to record user misconduct") from exc

    async def get_language(self, telegram_user_id: int) -> str:
        try:
            import asyncio
            response = await asyncio.to_thread(
                self._client.table("users")
                .select("language_code")
                .eq("telegram_user_id", telegram_user_id)
                .execute
            )
            data = getattr(response, "data", [])
            if not data:
                return "ar"
            return data[0].get("language_code", "ar")
        except Exception:
            return "ar"

    async def set_language(self, telegram_user_id: int, language_code: str) -> None:
        try:
            import asyncio
            await asyncio.to_thread(
                self._client.table("users")
                .update({"language_code": language_code})
                .eq("telegram_user_id", telegram_user_id)
                .execute
            )
        except Exception as exc:
            raise RuntimeError("failed to set user language") from exc

    async def get_all_user_telegram_ids(self) -> list[int]:
        try:
            import asyncio
            response = await asyncio.to_thread(
                self._client.table("users")
                .select("telegram_user_id")
                .eq("is_disabled", False)
                .execute
            )
            data = getattr(response, "data", [])
            return [row["telegram_user_id"] for row in data if "telegram_user_id" in row]
        except Exception as exc:
            raise RuntimeError("failed to fetch user ids") from exc

    async def get_admin_telegram_ids(self) -> list[int]:
        try:
            import asyncio
            response = await asyncio.to_thread(
                self._client.table("admin_authorizations")
                .select("telegram_user_id")
                .eq("is_revoked", False)
                .execute
            )
            data = getattr(response, "data", [])
            return [row["telegram_user_id"] for row in data if "telegram_user_id" in row]
        except Exception as exc:
            raise RuntimeError("failed to fetch admin ids") from exc

    async def unsuspend_user(self, admin_user_id: int, target_telegram_id: int) -> bool:
        try:
            import asyncio
            response = await asyncio.to_thread(
                self._client.rpc(
                    "admin_unsuspend_user",
                    {"p_admin_user_id": admin_user_id, "p_target_telegram_user_id": target_telegram_id}
                ).execute
            )
            return bool(getattr(response, "data", False))
        except Exception as exc:
            raise RuntimeError("failed to unsuspend user") from exc

    async def force_verify_user(self, admin_user_id: int, target_telegram_id: int) -> bool:
        try:
            import asyncio
            response = await asyncio.to_thread(
                self._client.rpc(
                    "admin_force_verify_user",
                    {"p_admin_user_id": admin_user_id, "p_target_telegram_user_id": target_telegram_id}
                ).execute
            )
            return bool(getattr(response, "data", False))
        except Exception as exc:
            raise RuntimeError("failed to force verify user") from exc

