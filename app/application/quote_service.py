from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.application.quote import PurchaseQuote
from app.application.quote_ports import ExchangeRateProvider, FeePolicyProvider, QuoteClock
from app.domain.currency import CurrencyCode, normalize_currency
from app.domain.money import OrderFinancials
from app.domain.network import normalize_network


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    network_code: str
    requested_amount: Decimal
    payment_currency: str


class QuoteService:
    def __init__(
        self,
        exchange_rates: ExchangeRateProvider,
        fee_policies: FeePolicyProvider,
        clock: QuoteClock,
        ttl: timedelta,
        rounding_policy_version: str,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("quote ttl must be positive")
        if not rounding_policy_version.strip():
            raise ValueError("rounding policy version is required")
        self._exchange_rates = exchange_rates
        self._fee_policies = fee_policies
        self._clock = clock
        self._ttl = ttl
        self._rounding_policy_version = rounding_policy_version

    async def create_quote(self, request: QuoteRequest) -> PurchaseQuote:
        issued_at = self._clock.now()
        if issued_at.tzinfo is None:
            raise RuntimeError("application clock must return a timezone-aware datetime")

        currency = normalize_currency(request.payment_currency)
        if currency is None:
            raise ValueError("unsupported payment currency")
        network = normalize_network(request.network_code)
        if network is None:
            raise ValueError("unsupported network")

        fee_policy = await self._fee_policies.get_current_policy(network.value, issued_at)
        if fee_policy is None:
            raise RuntimeError("current fee policy is unavailable")

        rate_snapshot = None
        exchange_rate = None
        if currency is CurrencyCode.NEW_SYP:
            rate_snapshot = await self._exchange_rates.get_current_rate(currency.value, issued_at)
            if rate_snapshot is None:
                raise RuntimeError("current exchange rate is unavailable")
            exchange_rate = rate_snapshot.rate

        financials = OrderFinancials.calculate(
            requested_amount=request.requested_amount,
            fee_percent=fee_policy.percent,
            payment_currency=currency.value,
            exchange_rate=exchange_rate,
            rounding_policy_version=self._rounding_policy_version,
        )

        return PurchaseQuote(
            financials=financials,
            exchange_rate_snapshot=rate_snapshot,
            fee_policy_snapshot=fee_policy,
            expires_at=issued_at + self._ttl,
        )

    def is_expired(self, quote: PurchaseQuote, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("comparison time must be timezone-aware")
        return now >= quote.expires_at
