from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup


@dataclass(frozen=True, slots=True)
class AdminPaymentAccount:
    id: str
    currency: CurrencyCode
    account_name: str
    account_number: str
    qr_image_file_id: str
    is_active: bool
    updated_at: datetime


class AdminPaymentAccountRepository(Protocol):
    async def list(self, admin_telegram_user_id: int, actor_type: str) -> list[AdminPaymentAccount]: ...

    async def upsert(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
    ) -> AdminPaymentAccount: ...

    async def set_active(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
    ) -> AdminPaymentAccount: ...


class AdminPaymentAccountService:
    """Application boundary for administrator management of receiving accounts."""

    def __init__(self, repository: AdminPaymentAccountRepository) -> None:
        self._repository = repository

    @staticmethod
    def _validate_admin(admin_telegram_user_id: int, actor_type: str) -> str:
        if not isinstance(admin_telegram_user_id, int) or admin_telegram_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        if not isinstance(actor_type, str):
            raise ValueError("administrator actor type is required")
        normalized = actor_type.strip().lower()
        if normalized not in {"primary", "backup"}:
            raise ValueError("invalid administrator actor type")
        return normalized

    async def list(self, admin_telegram_user_id: int, actor_type: str) -> list[AdminPaymentAccount]:
        normalized_actor = self._validate_admin(admin_telegram_user_id, actor_type)
        return await self._repository.list(admin_telegram_user_id, normalized_actor)

    async def upsert(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        setup: PaymentMethodSetup,
    ) -> AdminPaymentAccount:
        normalized_actor = self._validate_admin(admin_telegram_user_id, actor_type)
        if not isinstance(currency, CurrencyCode):
            raise ValueError("payment currency is required")
        if not isinstance(setup, PaymentMethodSetup):
            raise ValueError("payment method setup is required")
        return await self._repository.upsert(
            admin_telegram_user_id, normalized_actor, currency, setup
        )

    async def set_active(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        currency: CurrencyCode,
        is_active: bool,
    ) -> AdminPaymentAccount:
        normalized_actor = self._validate_admin(admin_telegram_user_id, actor_type)
        if not isinstance(currency, CurrencyCode):
            raise ValueError("payment currency is required")
        if not isinstance(is_active, bool):
            raise ValueError("active state must be boolean")
        return await self._repository.set_active(
            admin_telegram_user_id, normalized_actor, currency, is_active
        )
