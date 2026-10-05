from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.currency import CurrencyCode, normalize_currency
from app.domain.receipt_verification import ABSOLUTE_TOLERANCE


@dataclass(frozen=True, slots=True)
class ReceiptVerificationContext:
    order_id: UUID
    payment_currency: CurrencyCode | str
    expected_payment_amount: Decimal
    exchange_rate: Decimal | None
    fee_percent: Decimal
    rounding_policy_version: str
    network_code: str
    wallet_address: str
    expected_reference: str | None = None
    tolerance: Decimal = ABSOLUTE_TOLERANCE

    def __post_init__(self) -> None:
        normalized_currency = normalize_currency(str(self.payment_currency))
        if normalized_currency is None:
            raise ValueError("unsupported payment currency")
        object.__setattr__(self, "payment_currency", normalized_currency)

        if not self.expected_payment_amount.is_finite() or self.expected_payment_amount <= 0:
            raise ValueError("expected payment amount must be positive and finite")
        if self.payment_currency is CurrencyCode.NEW_SYP and (self.exchange_rate is None or not self.exchange_rate.is_finite() or self.exchange_rate <= 0):
            raise ValueError("NEW.SYP verification requires exchange rate snapshot")
        if self.payment_currency is CurrencyCode.USD and self.exchange_rate is not None:
            raise ValueError("USD verification must not carry an exchange rate")
        if not self.fee_percent.is_finite() or self.fee_percent < 0 or self.fee_percent >= 100:
            raise ValueError("invalid fee percent")
        if not self.rounding_policy_version.strip():
            raise ValueError("rounding policy version is required")
        if not self.network_code.strip():
            raise ValueError("network code is required")
        if not self.wallet_address.strip():
            raise ValueError("wallet address snapshot is required")
        if self.expected_reference is not None and not self.expected_reference.strip():
            raise ValueError("expected reference cannot be blank")
        if not self.tolerance.is_finite() or self.tolerance < 0:
            raise ValueError("tolerance must be finite and non-negative")
