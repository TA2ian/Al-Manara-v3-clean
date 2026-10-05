from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.currency import CurrencyCode
from app.domain.network import NetworkConfig
from app.domain.order import Order
from app.domain.order_draft import PurchaseOrderDraft
from app.domain.order_status import OrderStatus
from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity
from app.domain.wallet import Wallet


@dataclass(frozen=True, slots=True)
class PersistedOrderCreation:
    internal_order_id: UUID
    public_order_code: str
    status: OrderStatus
    version: int
    replayed: bool


class CustomerRepository(Protocol):
    async def get_payment_identity(self, user_id: int) -> CustomerPaymentIdentity | None: ...


class PaymentSettingsRepository(Protocol):
    async def get_admin_payment_account(
        self, currency: CurrencyCode
    ) -> AdminPaymentAccountSnapshot | None: ...


class WalletOrderRepository(Protocol):
    async def get_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None: ...
    async def get_verified_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None: ...
    async def get_or_create_wallet_for_user(self, user_id: int, address: str, network: str) -> Wallet: ...


class NetworkOrderRepository(Protocol):
    async def get_enabled(self, code: str) -> NetworkConfig | None: ...


class PublicOrderCodeGenerator(Protocol):
    def generate(self) -> str: ...


class OrderCreationRepository(Protocol):
    async def create_order_atomically(self, draft: PurchaseOrderDraft) -> PersistedOrderCreation: ...
