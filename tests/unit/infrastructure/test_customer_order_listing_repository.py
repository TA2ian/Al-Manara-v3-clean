from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.order_status import OrderStatus
from app.infrastructure.persistence.customer_order_listing_repository import (
    CustomerOrderListingPersistenceError,
    SupabaseCustomerOrderListingRepository,
)


class FakeQuery:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeResponse:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.responses[function_name])


@pytest.mark.asyncio
async def test_repository_maps_only_customer_safe_order_fields():
    client = FakeClient(
        {
            "count_customer_orders": FakeResponse([{"total_count": 1}]),
            "list_customer_orders": FakeResponse(
                [
                {
                    "public_order_code": "ORD-123",
                    "status": "PENDING_PAYMENT",
                    "version": 3,
                    "network_code": "BEP20",
                    "requested_amount": "15.500",
                    "payment_currency": "NEW.SYP",
                    "local_amount": "155000.00",
                    "created_at": "2026-09-05T10:00:00+00:00",
                    "total_count": 1,
                }
                ]
            ),
        }
    )

    page = await SupabaseCustomerOrderListingRepository(client).list_orders(123, 0, 10)

    assert client.calls == [
        ("count_customer_orders", {"p_telegram_user_id": 123}),
        (
            "list_customer_orders",
            {"p_telegram_user_id": 123, "p_page": 0, "p_page_size": 10},
        )
    ]
    assert page.total_count == 1
    assert page.items[0].public_order_code == "ORD-123"
    assert page.items[0].status is OrderStatus.PENDING_PAYMENT
    assert page.items[0].requested_amount == Decimal("15.500")
    assert page.items[0].created_at == datetime(2026, 9, 5, 10, tzinfo=timezone.utc)
    assert not hasattr(page.items[0], "internal_order_id")
    assert not hasattr(page.items[0], "wallet_id")


@pytest.mark.asyncio
async def test_repository_rejects_invalid_payload():
    client = FakeClient(
        {
            "count_customer_orders": FakeResponse([{"total_count": 1}]),
            "list_customer_orders": FakeResponse([{"public_order_code": "ORD-123"}]),
        }
    )

    with pytest.raises(CustomerOrderListingPersistenceError, match="invalid customer"):
        await SupabaseCustomerOrderListingRepository(client).list_orders(123, 0, 5)


@pytest.mark.asyncio
async def test_repository_hides_rpc_errors():
    client = FakeClient(
        {"count_customer_orders": FakeResponse(error={"message": "database detail"})}
    )

    with pytest.raises(CustomerOrderListingPersistenceError, match="returned an error"):
        await SupabaseCustomerOrderListingRepository(client).list_orders(123, 0, 5)


@pytest.mark.asyncio
async def test_repository_keeps_total_count_for_an_empty_page():
    client = FakeClient(
        {
            "count_customer_orders": FakeResponse([{"total_count": 2}]),
            "list_customer_orders": FakeResponse([]),
        }
    )

    page = await SupabaseCustomerOrderListingRepository(client).list_orders(123, 4, 5)

    assert page.items == ()
    assert page.total_count == 2