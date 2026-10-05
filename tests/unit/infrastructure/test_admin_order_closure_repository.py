from uuid import uuid4

import pytest

from app.infrastructure.persistence.admin_order_closure_repository import (
    AdminOrderClosurePersistenceError,
    SupabaseAdminOrderClosureRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class Response:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeQuery(self.response)


@pytest.mark.asyncio
async def test_maps_closure_rpc_result() -> None:
    order_id = uuid4()
    session_id = uuid4()
    client = FakeClient(
        Response(
            [{
                "internal_order_id": str(order_id),
                "public_order_code": "ORD-CLOSE02",
                "status": "CLOSED_WITHOUT_FULFILLMENT",
                "version": 8,
                "replayed": False,
            }]
        )
    )

    result = await SupabaseAdminOrderClosureRepository(client).close_without_fulfillment(
        order_id, 7, 100, session_id, "no fulfillment", "close-2"
    )

    assert result.internal_order_id == order_id
    assert result.status == "CLOSED_WITHOUT_FULFILLMENT"
    assert result.version == 8
    assert client.calls[0][0] == "close_order_without_fulfillment"
    assert client.calls[0][1]["p_session_id"] == str(session_id)


@pytest.mark.asyncio
async def test_rejects_malformed_closure_payload() -> None:
    client = FakeClient(Response([{"status": "CLOSED_WITHOUT_FULFILLMENT"}]))

    with pytest.raises(AdminOrderClosurePersistenceError):
        await SupabaseAdminOrderClosureRepository(client).close_without_fulfillment(
            uuid4(), 1, 100, uuid4(), "reason", "close-3"
        )
