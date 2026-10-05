from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.money import OrderFinancials
from app.domain.network import NetworkCode
from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity


@dataclass(frozen=True, slots=True)
class PurchaseOrderDraft:
    internal_order_id: UUID
    public_order_code: str
    user_id: int
    wallet_id: UUID
    network: NetworkCode
    wallet_address: str
    customer_payment_identity: CustomerPaymentIdentity
    admin_payment_account: AdminPaymentAccountSnapshot
    financials: OrderFinancials
    quote_issued_at: datetime
    quote_expires_at: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.quote_issued_at.tzinfo is None or self.quote_expires_at.tzinfo is None:
            raise ValueError("quote timestamps must be timezone-aware")
        if self.quote_expires_at <= self.quote_issued_at:
            raise ValueError("quote expiry must be after quote issuance")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency key is required")
