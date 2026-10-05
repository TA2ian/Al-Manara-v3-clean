from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from app.domain.currency import CurrencyCode
from app.domain.network import NetworkCode, NetworkConfig
from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class OrderSupportPersistenceError(RuntimeError):
    """Raised when an order-support persistence operation returns invalid data or fails."""


class SupabaseCustomerRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_payment_identity(self, user_id: int) -> CustomerPaymentIdentity | None:
        rows = await self._rpc(
            "get_customer_payment_identity",
            {"p_telegram_user_id": user_id},
        )
        if not rows:
            return None
        try:
            return CustomerPaymentIdentity(
                verified_name=str(rows[0]["verified_name"]),
                verified_shamcash_account=str(rows[0]["verified_shamcash_account"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrderSupportPersistenceError("invalid customer identity payload") from exc

    async def _rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return await _execute_rpc(self._client, function_name, params)


class SupabasePaymentSettingsRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_admin_payment_account(
        self, currency: CurrencyCode
    ) -> AdminPaymentAccountSnapshot | None:
        rows = await _execute_rpc(
            self._client,
            "get_admin_payment_account",
            {"p_currency": currency.value},
        )
        if not rows:
            return None
        try:
            return AdminPaymentAccountSnapshot(
                account_name=str(rows[0]["account_name"]),
                account_number=str(rows[0]["account_number"]),
                qr_image_file_id=str(rows[0]["qr_image_file_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrderSupportPersistenceError("invalid admin payment account payload") from exc


class SupabaseNetworkOrderRepository:
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_enabled(self, code: str) -> NetworkConfig | None:
        rows = await _execute_rpc(
            self._client,
            "get_network_config",
            {"p_code": code.strip().upper()},
        )
        if not rows:
            return None
        try:
            row = rows[0]
            network_code = NetworkCode(str(row["code"]))
            return NetworkConfig(
                code=network_code,
                display_name=str(row["display_name"]),
                enabled=bool(row["enabled"]),
                address_regex=str(row["address_regex"]),
                requires_memo=bool(row["requires_memo"]),
                min_amount=_decimal(row["min_amount"], "min_amount"),
                max_amount=_decimal(row["max_amount"], "max_amount"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrderSupportPersistenceError("invalid network config payload") from exc


async def _execute_rpc(
    client: SupabaseRpcClient,
    function_name: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        response = await asyncio.to_thread(client.rpc(function_name, params).execute)
    except Exception as exc:
        raise OrderSupportPersistenceError(
            f"order-support persistence RPC failed: {function_name}"
        ) from exc

    error = getattr(response, "error", None)
    if error:
        raise OrderSupportPersistenceError(_error_message(error))
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise OrderSupportPersistenceError(
            f"RPC returned invalid data: {function_name}"
        )
    return [dict(row) for row in data if isinstance(row, dict)]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal field: {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid decimal field: {field}")
    return result


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
