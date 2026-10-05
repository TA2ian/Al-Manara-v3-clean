from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.application.quote import ExchangeRateSnapshot, FeePolicySnapshot


class ExchangeRateProvider(Protocol):
    async def get_current_rate(self, currency: str, now: datetime) -> ExchangeRateSnapshot | None: ...


class FeePolicyProvider(Protocol):
    async def get_current_policy(self, network_code: str, now: datetime) -> FeePolicySnapshot | None: ...


class RoundingPolicyProvider(Protocol):
    async def get_current_version(self) -> str: ...


class QuoteClock(Protocol):
    def now(self) -> datetime: ...
