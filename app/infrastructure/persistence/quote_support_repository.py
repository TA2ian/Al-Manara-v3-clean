from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import uuid4

from app.application.quote import ExchangeRateSnapshot, FeePolicySnapshot
from app.application.quote_ports import ExchangeRateProvider, FeePolicyProvider, QuoteClock, RoundingPolicyProvider


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class QuoteSupportPersistenceError(RuntimeError):
    """Raised when an authoritative quote-support RPC fails or returns invalid data."""


class SupabaseFeePolicyProvider(FeePolicyProvider):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_current_policy(self, network_code: str, now: datetime) -> FeePolicySnapshot | None:
        rows = await _execute_rpc(self._client, "get_current_fee_policy", {"p_network_code": network_code.strip().upper(), "p_now": now.isoformat()})
        if not rows:
            return None
        try:
            row = rows[0]
            return FeePolicySnapshot(
                percent=_decimal(row["percent"], "percent"),
                version=str(row["version"]),
                effective_at=_datetime(row["effective_at"], "effective_at"),
                fixed_network_fee_usdt=_decimal(row.get("fixed_network_fee_usdt", "0"), "fixed_network_fee_usdt"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise QuoteSupportPersistenceError("invalid fee policy payload") from exc


class SupabaseExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_current_rate(self, currency: str, now: datetime) -> ExchangeRateSnapshot | None:
        rows = await _execute_rpc(self._client, "get_current_exchange_rate", {"p_currency": currency.strip().upper(), "p_now": now.isoformat()})
        if not rows:
            return None
        try:
            row = rows[0]
            return ExchangeRateSnapshot(currency=str(row["currency"]), rate=_decimal(row["rate"], "rate"), captured_at=_datetime(row["captured_at"], "captured_at"), source=str(row["source"]), version=str(row["version"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise QuoteSupportPersistenceError("invalid exchange rate payload") from exc


class SupabaseRoundingPolicyProvider(RoundingPolicyProvider):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def get_current_version(self) -> str:
        rows = await _execute_rpc(self._client, "get_current_rounding_policy", {})
        if len(rows) != 1:
            raise QuoteSupportPersistenceError("current rounding policy payload is invalid")
        version = rows[0].get("version")
        if not isinstance(version, str) or not version.strip():
            raise QuoteSupportPersistenceError("current rounding policy version is invalid")
        return version.strip()


class UtcQuoteClock(QuoteClock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidPublicOrderCodeGenerator:
    def __init__(self, prefix: str = "ORD") -> None:
        normalized = prefix.strip().upper()
        if not normalized or len(normalized) > 12:
            raise ValueError("order code prefix must contain 1-12 characters")
        self._prefix = normalized

    def generate(self) -> str:
        return f"{self._prefix}-{uuid4().hex[:12].upper()}"


async def _execute_rpc(client: SupabaseRpcClient, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = await asyncio.to_thread(client.rpc(function_name, params).execute)
    except Exception as exc:
        raise QuoteSupportPersistenceError(f"quote-support persistence RPC failed: {function_name}") from exc
    error = getattr(response, "error", None)
    if error:
        raise QuoteSupportPersistenceError(_error_message(error))
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise QuoteSupportPersistenceError(f"RPC returned invalid data: {function_name}")
    return [dict(row) for row in data if isinstance(row, dict)]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal field: {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid decimal field: {field}")
    return result


def _datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"invalid datetime field: {field}")
    if result.tzinfo is None:
        raise ValueError(f"invalid datetime field: {field}")
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
