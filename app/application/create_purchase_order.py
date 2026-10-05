from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.order_creation_ports import (
    CustomerRepository,
    NetworkOrderRepository,
    OrderCreationRepository,
    PaymentSettingsRepository,
    PublicOrderCodeGenerator,
    WalletOrderRepository,
)
from app.application.quote import PurchaseQuote
from app.application.quote_ports import ExchangeRateProvider, FeePolicyProvider, QuoteClock, RoundingPolicyProvider
from app.domain.currency import CurrencyCode, normalize_currency
from app.domain.money import OrderFinancials
from app.domain.network import normalize_network
from app.domain.order_draft import PurchaseOrderDraft
from app.domain.payment_identity import AdminPaymentAccountSnapshot
from app.domain.payment_identity import CustomerPaymentIdentity
from app.domain.wallet_selection import validate_wallet_for_order

DEFAULT_QUOTE_TTL = timedelta(minutes=10)

@dataclass(frozen=True, slots=True)
class CreatePurchaseOrderCommand:
    user_id: int
    wallet_id: UUID
    network_code: str
    requested_amount: Decimal
    payment_currency: str
    idempotency_key: str

class CreatePurchaseOrderService:
    def __init__(self, customers: CustomerRepository, wallets: WalletOrderRepository, networks: NetworkOrderRepository, payments: PaymentSettingsRepository, orders: OrderCreationRepository, public_codes: PublicOrderCodeGenerator, exchange_rates: ExchangeRateProvider, fee_policies: FeePolicyProvider, rounding_policies: RoundingPolicyProvider, clock: QuoteClock, quote_ttl: timedelta = DEFAULT_QUOTE_TTL) -> None:
        if quote_ttl <= timedelta(0):
            raise ValueError("quote ttl must be positive")
        self._customers = customers
        self._wallets = wallets
        self._networks = networks
        self._payments = payments
        self._orders = orders
        self._public_codes = public_codes
        self._exchange_rates = exchange_rates
        self._fee_policies = fee_policies
        self._rounding_policies = rounding_policies
        self._clock = clock
        self._quote_ttl = quote_ttl

    async def preview(self, command: CreatePurchaseOrderCommand) -> PurchaseQuote:
        """Validate the complete order context and calculate a non-persistent quote."""
        now = self._clock.now()
        _, _, _, _, quote = await self._prepare(command, now)
        return quote

    async def create(self, command: CreatePurchaseOrderCommand, provided_quote: PurchaseQuote | None = None) -> object:
        now = self._clock.now()
        identity, wallet, network, payment_account, new_quote = await self._prepare(command, now)
        
        quote = provided_quote or new_quote
        if provided_quote:
            if now > provided_quote.expires_at:
                raise ValueError("Quote has expired")
            # We still need to ensure the values match if we want to be super strict,
            # but using provided_quote guarantees price snapshot is frozen.
        draft = PurchaseOrderDraft(
            internal_order_id=uuid4(),
            public_order_code=self._public_codes.generate(),
            user_id=command.user_id,
            wallet_id=wallet.wallet_id,
            network=network.code,
            wallet_address=wallet.address,
            customer_payment_identity=identity,
            admin_payment_account=AdminPaymentAccountSnapshot(account_name=payment_account.account_name, account_number=payment_account.account_number, qr_image_file_id=payment_account.qr_image_file_id),
            financials=quote.financials,
            quote_issued_at=now,
            quote_expires_at=quote.expires_at,
            idempotency_key=command.idempotency_key.strip(),
        )
        return await self._orders.create_order_atomically(draft)

    async def _prepare(self, command: CreatePurchaseOrderCommand, now: datetime):
        if now.tzinfo is None:
            raise RuntimeError("application clock must return a timezone-aware datetime")
        if not command.idempotency_key.strip():
            raise ValueError("idempotency key is required")
        currency = normalize_currency(command.payment_currency)
        if currency is None:
            raise ValueError("unsupported payment currency")
        network_code = normalize_network(command.network_code)
        if network_code is None:
            raise ValueError("unsupported network")
        identity = await self._customers.get_payment_identity(command.user_id)
        if identity is None:
            # Unverified customers tier limits: 10 - 50 USDT
            if command.requested_amount < Decimal("10") or command.requested_amount > Decimal("50"):
                raise ValueError("العملاء غير الموثقين يمكنهم الطلب بين 10 و 50 دولار فقط")
            identity = CustomerPaymentIdentity(
                verified_name="UNVERIFIED",
                verified_shamcash_account="UNVERIFIED"
            )

        wallet = await self._wallets.get_for_user(command.wallet_id, command.user_id)
        if wallet is None:
            # Fallback to get_verified_for_user if get_for_user returns None
            wallet = await self._wallets.get_verified_for_user(command.wallet_id, command.user_id)
        if wallet is None:
            raise LookupError("wallet not found for customer")
        network = await self._networks.get_enabled(network_code.value)
        if network is None or not network.enabled:
            raise ValueError("selected network is unavailable")
        validate_wallet_for_order(wallet, command.user_id, network, command.requested_amount)
        payment_account = await self._payments.get_admin_payment_account(currency)
        if payment_account is None:
            raise RuntimeError("admin payment account is not configured")
        fee_policy = await self._fee_policies.get_current_policy(network.code.value, now)
        if fee_policy is None:
            raise RuntimeError("current fee policy is unavailable")
        rounding_policy_version = await self._rounding_policies.get_current_version()
        if not rounding_policy_version.strip():
            raise RuntimeError("current rounding policy is unavailable")
        rate_snapshot = None
        exchange_rate = None
        if currency is CurrencyCode.NEW_SYP:
            rate_snapshot = await self._exchange_rates.get_current_rate(currency.value, now)
            if rate_snapshot is None:
                raise RuntimeError("current exchange rate is unavailable")
            exchange_rate = rate_snapshot.rate
        financials = OrderFinancials.calculate(
            requested_amount=command.requested_amount,
            fee_percent=fee_policy.percent,
            payment_currency=currency.value,
            exchange_rate=exchange_rate,
            rounding_policy_version=rounding_policy_version,
            network_fixed_fee_usdt=fee_policy.fixed_network_fee_usdt,
        )
        quote = PurchaseQuote(financials=financials, exchange_rate_snapshot=rate_snapshot, fee_policy_snapshot=fee_policy, expires_at=now + self._quote_ttl)
        return identity, wallet, network, payment_account, quote
