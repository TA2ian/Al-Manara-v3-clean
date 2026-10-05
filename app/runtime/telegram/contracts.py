"""Transport-level contracts for the Telegram runtime.

These dataclasses carry validated, parsed data between the Telegram layer
and the application layer. They must not import domain or infrastructure modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final
from uuid import UUID

MAX_IDEMPOTENCY_KEY_LENGTH: Final[int] = 128


@dataclass(frozen=True, slots=True)
class TelegramOrderInput:
    """Validated data collected by the Telegram order creation flow."""

    user_id: int
    wallet_id: UUID
    network_code: str
    requested_amount: Decimal
    payment_currency: str
    idempotency_key: str

    @classmethod
    def from_values(
        cls,
        *,
        user_id: int,
        wallet_id: str,
        network_code: str,
        requested_amount: str,
        payment_currency: str,
        idempotency_key: str,
    ) -> "TelegramOrderInput":
        if user_id <= 0:
            raise ValueError("invalid Telegram user id")
        try:
            parsed_wallet_id = UUID(wallet_id.strip())
        except (AttributeError, ValueError):
            raise ValueError("invalid wallet id") from None
        try:
            amount = Decimal(requested_amount.strip())
        except (AttributeError, InvalidOperation):
            raise ValueError("invalid amount") from None
        if not amount.is_finite() or amount <= 0:
            raise ValueError("amount must be positive and finite")
        key = idempotency_key.strip()
        if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("invalid idempotency key")
        network = network_code.strip()
        currency = payment_currency.strip()
        if not network:
            raise ValueError("network is required")
        if not currency:
            raise ValueError("payment currency is required")
        return cls(
            user_id=user_id,
            wallet_id=parsed_wallet_id,
            network_code=network,
            requested_amount=amount,
            payment_currency=currency,
            idempotency_key=key,
        )


@dataclass(frozen=True, slots=True)
class TelegramOrderResponse:
    """Transport-neutral response produced by the order handler."""

    ok: bool
    text: str
    order_code: str | None = None
