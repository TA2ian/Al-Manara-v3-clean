from __future__ import annotations

import asyncio
from typing import Any, Protocol
from uuid import UUID

from app.domain.network import NetworkCode
from app.domain.wallet import Wallet, WalletStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class WalletPersistenceError(RuntimeError):
    """Raised when the wallet persistence boundary cannot complete an operation."""


class SupabaseWalletRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None:
        rows = await self._rpc("get_wallet_for_telegram_user", {"p_wallet_id": str(wallet_id), "p_telegram_user_id": user_id})
        if not rows:
            return None
        return self._map_wallet(rows[0])

    async def get_verified_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None:
        wallet = await self.get_for_user(wallet_id, user_id)
        if wallet is None or wallet.status is not WalletStatus.VERIFIED:
            return None
        return wallet

    async def list_verified_for_user(self, user_id: int) -> tuple[Wallet, ...]:
        rows = await self._rpc("list_verified_wallets_for_telegram_user", {"p_telegram_user_id": user_id})
        return tuple(self._map_wallet(row) for row in rows)

    async def find_verified_by_address(self, address: str) -> Wallet | None:
        rows = await self._rpc("find_verified_wallet_by_address", {"p_address": address.strip()})
        if not rows:
            return None
        return self._map_wallet(rows[0])

    async def get_or_create_wallet_for_user(self, user_id: int, address: str, network: str) -> Wallet:
        normalized = address.strip()
        net = network.strip().upper()
        # 1. Check existing wallet
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("wallets")
                .select("id, address, network_code, status, users!inner(telegram_user_id)")
                .eq("users.telegram_user_id", user_id)
                .eq("network_code", net)
                .eq("normalized_address", normalized)
                .execute()
            )
            if res.data:
                row = res.data[0]
                return Wallet(
                    wallet_id=UUID(str(row["id"])),
                    user_id=user_id,
                    network=NetworkCode(net),
                    address=str(row["address"]),
                    status=WalletStatus(str(row["status"]).strip().lower()),
                )
        except Exception:
            pass

        # 2. If not found, look up internal user id to insert new wallet
        u_res = await asyncio.to_thread(
            lambda: self._client.table("users").select("id").eq("telegram_user_id", user_id).single().execute()
        )
        internal_user_id = u_res.data["id"]

        insert_res = await asyncio.to_thread(
            lambda: self._client.table("wallets").insert({
                "user_id": internal_user_id,
                "network_code": net,
                "address": normalized,
                "normalized_address": normalized,
                "status": "VERIFIED"
            }).execute()
        )
        new_row = insert_res.data[0]
        return Wallet(
            wallet_id=UUID(str(new_row["id"])),
            user_id=user_id,
            network=NetworkCode(net),
            address=str(new_row["address"]),
            status=WalletStatus(str(new_row["status"]).strip().lower()),
        )

    async def create_pending(self, *, user_id: int, address: str, network: str, qr_image_file_id: str, label: str) -> Wallet:
        rows = await self._rpc(
            "register_pending_wallet_for_telegram_user",
            {
                "p_telegram_user_id": user_id,
                "p_address": address,
                "p_network_code": network,
                "p_qr_image_file_id": qr_image_file_id,
                "p_label": label,
            },
        )
        if len(rows) != 1:
            raise WalletPersistenceError("wallet registration RPC returned an invalid payload")
        return self._map_wallet(rows[0])

    async def disable_verified_for_user(self, wallet_id: UUID, user_id: int) -> bool:
        rows = await self._rpc("disable_wallet_for_telegram_user", {"p_wallet_id": str(wallet_id), "p_telegram_user_id": user_id})
        if len(rows) != 1 or "disabled" not in rows[0]:
            raise WalletPersistenceError("wallet disable RPC returned an invalid payload")
        value = rows[0]["disabled"]
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise WalletPersistenceError("wallet disable RPC returned an invalid boolean")

    async def _rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(self._client.rpc(function_name, params).execute)
        except Exception as exc:
            raise WalletPersistenceError(f"wallet persistence RPC failed: {function_name}") from exc
        error = getattr(response, "error", None)
        if error:
            raise WalletPersistenceError(self._error_message(error))
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise WalletPersistenceError(f"wallet RPC returned invalid data: {function_name}")
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _map_wallet(row: dict[str, Any]) -> Wallet:
        try:
            return Wallet(
                wallet_id=UUID(str(row["wallet_id"])),
                user_id=int(row["telegram_user_id"]),
                network=NetworkCode(str(row["network_code"]).strip().upper()),
                address=str(row["address"]),
                status=WalletStatus(str(row["status"]).strip().lower()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WalletPersistenceError("invalid wallet persistence payload") from exc

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
