from datetime import datetime
from uuid import uuid4

import pytest

from app.domain.order_status import OrderStatus
from app.infrastructure.persistence.order_repository import (
    OrderPersistenceError,
    SupabaseOrderRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.responses[function_name])


class Response:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


@pytest.mark.asyncio
async def test_get_order_maps_postgres_payload() -> None:
    order_id = uuid4()
    client = FakeClient(
        {
            "get_order_for_transition": Response(
                [
                    {
                        "internal_order_id": str(order_id),
                        "public_order_code": "ORD-1001",
                        "status": "UNDER_REVIEW",
                        "version": 7,
                    }
                ]
            )
        }
    )

    order = await SupabaseOrderRepository(client).get_for_update(order_id)

    assert order is not None
    assert order.internal_order_id == order_id
    assert order.public_order_code == "ORD-1001"
    assert order.status is OrderStatus.UNDER_REVIEW
    assert order.version == 7


@pytest.mark.asyncio
async def test_transition_propagates_admin_actor_and_event_payload() -> None:
    order_id = uuid4()
    client = FakeClient(
        {
            "transition_order_if_version": Response(
                [
                    {
                        "internal_order_id": str(order_id),
                        "public_order_code": "ORD-1002",
                        "status": "APPROVED",
                        "version": 8,
                    }
                ]
            )
        }
    )

    result = await SupabaseOrderRepository(client).transition_if_version(
        order_id,
        OrderStatus.APPROVED,
        7,
        actor_telegram_user_id=123,
        actor_type="primary",
        event_payload={"reason": "reviewed"},
    )

    assert result is not None
    assert result.order.status is OrderStatus.APPROVED
    assert result.order.version == 8
    assert client.calls == [
        (
            "transition_order_if_version",
            {
                "p_order_id": str(order_id),
                "p_target_status": "APPROVED",
                "p_expected_version": 7,
                "p_actor_telegram_user_id": 123,
                "p_actor_type": "primary",
                "p_event_payload": {"reason": "reviewed"},
            },
        )
    ]
    assert isinstance(result.transitioned_at, datetime)


@pytest.mark.asyncio
async def test_invalid_rpc_payload_is_rejected() -> None:
    order_id = uuid4()
    client = FakeClient(
        {
            "get_order_for_transition": Response(
                [{"internal_order_id": str(order_id), "status": "UNKNOWN", "version": 1}]
            )
        }
    )

    with pytest.raises(OrderPersistenceError):
        await SupabaseOrderRepository(client).get_for_update(order_id)
