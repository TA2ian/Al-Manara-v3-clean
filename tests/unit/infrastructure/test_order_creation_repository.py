from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.money import OrderFinancials
from app.domain.network import NetworkCode
from app.domain.order_draft import PurchaseOrderDraft
from app.domain.order_status import OrderStatus
from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity
from app.infrastructure.persistence.order_creation_repository import (
    OrderCreationPersistenceError,
    SupabaseOrderCreationRepository,
)


class FakeResponse:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.response)


def draft() -> PurchaseOrderDraft:
    issued = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
    return PurchaseOrderDraft(
        internal_order_id=uuid4(),
        public_order_code="ORD-TEST1",
        user_id=123,
        wallet_id=uuid4(),
        network=NetworkCode.TRC20,
        wallet_address="T9yD14Nj9j7xAB4dbGeiX9h8unkM4Jx7nQ",
        customer_payment_identity=CustomerPaymentIdentity("Customer", "0900000000"),
        admin_payment_account=AdminPaymentAccountSnapshot("Al-Manara", "0900000001", "qr-file"),
        financials=OrderFinancials.calculate(
            Decimal("100"), Decimal("5"), "NEW.SYP", Decimal("135"), "v1"
        ),
        quote_issued_at=issued,
        quote_expires_at=datetime(2026, 8, 29, 8, 10, tzinfo=timezone.utc),
        idempotency_key="order:create:123",
    )


@pytest.mark.asyncio
async def test_atomic_order_creation_maps_rpc_payload_and_sends_snapshots() -> None:
    order_id = uuid4()
    client = FakeClient(
        FakeResponse(
            data=[
                {
                    "internal_order_id": str(order_id),
                    "public_order_code": "ORD-TEST1",
                    "status": "DRAFT",
                    "version": 1,
                    "replayed": False,
                }
            ]
        )
    )

    result = await SupabaseOrderCreationRepository(client).create_order_atomically(draft())

    assert result.internal_order_id == order_id
    assert result.status is OrderStatus.DRAFT
    assert result.replayed is False
    assert client.calls[0][0] == "create_purchase_order_atomic"
    assert client.calls[0][1]["p_payment_currency"] == "NEW.SYP"
    assert client.calls[0][1]["p_quote_expires_at"].endswith("+00:00")
    assert client.calls[0][1]["p_idempotency_key"] == "order:create:123"


@pytest.mark.asyncio
async def test_atomic_order_creation_rejects_malformed_payload() -> None:
    client = FakeClient(FakeResponse(data=[]))

    with pytest.raises(OrderCreationPersistenceError, match="invalid payload"):
        await SupabaseOrderCreationRepository(client).create_order_atomically(draft())
