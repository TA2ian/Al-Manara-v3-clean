from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Any

from app.domain.money import OrderFinancials


@dataclass(frozen=True, slots=True)
class ExchangeRateSnapshot:
    currency: str
    rate: Decimal
    captured_at: datetime
    source: str
    version: str

    def __post_init__(self) -> None:
        if not self.rate.is_finite() or self.rate <= 0:
            raise ValueError("exchange rate must be positive and finite")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if not self.source.strip():
            raise ValueError("exchange rate source is required")
        if not self.version.strip():
            raise ValueError("exchange rate version is required")


@dataclass(frozen=True, slots=True)
class FeePolicySnapshot:
    percent: Decimal
    version: str
    effective_at: datetime
    fixed_network_fee_usdt: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.percent < 0 or self.percent >= 100:
            raise ValueError("fee percent must be in [0, 100)")
        if not self.fixed_network_fee_usdt.is_finite() or self.fixed_network_fee_usdt < 0:
            raise ValueError("fixed network fee must be finite and non-negative")
        if self.effective_at.tzinfo is None:
            raise ValueError("effective_at must be timezone-aware")
        if not self.version.strip():
            raise ValueError("fee policy version is required")


@dataclass(frozen=True, slots=True)
class PurchaseQuote:
    financials: OrderFinancials
    exchange_rate_snapshot: ExchangeRateSnapshot | None
    fee_policy_snapshot: FeePolicySnapshot
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("quote expiry must be timezone-aware")
        if self.exchange_rate_snapshot is None and self.financials.payment_currency != "USD":
            raise ValueError("non-USD quote requires exchange rate snapshot")

    def to_dict(self) -> dict[str, Any]:
        return {
            "financials": self.financials.to_dict(),
            "exchange_rate_snapshot": {
                "currency": self.exchange_rate_snapshot.currency,
                "rate": str(self.exchange_rate_snapshot.rate),
                "captured_at": self.exchange_rate_snapshot.captured_at.isoformat(),
                "source": self.exchange_rate_snapshot.source,
                "version": self.exchange_rate_snapshot.version,
            } if self.exchange_rate_snapshot else None,
            "fee_policy_snapshot": {
                "percent": str(self.fee_policy_snapshot.percent),
                "version": self.fee_policy_snapshot.version,
                "effective_at": self.fee_policy_snapshot.effective_at.isoformat(),
                "fixed_network_fee_usdt": str(self.fee_policy_snapshot.fixed_network_fee_usdt),
            },
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PurchaseQuote:
        ers_data = data.get("exchange_rate_snapshot")
        ers = ExchangeRateSnapshot(
            currency=ers_data["currency"],
            rate=Decimal(ers_data["rate"]),
            captured_at=datetime.fromisoformat(ers_data["captured_at"]),
            source=ers_data["source"],
            version=ers_data["version"],
        ) if ers_data else None

        fps_data = data["fee_policy_snapshot"]
        fps = FeePolicySnapshot(
            percent=Decimal(fps_data["percent"]),
            version=fps_data["version"],
            effective_at=datetime.fromisoformat(fps_data["effective_at"]),
            fixed_network_fee_usdt=Decimal(fps_data.get("fixed_network_fee_usdt", "0")),
        )

        return cls(
            financials=OrderFinancials.from_dict(data["financials"]),
            exchange_rate_snapshot=ers,
            fee_policy_snapshot=fps,
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
