import pytest

from app.infrastructure.persistence.admin_authorization_repository import (
    AdminAuthorizationPersistenceError,
    SupabaseAdminAuthorizationRepository,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeResponse:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def rpc(self, function_name, params):
        self.calls.append((function_name, params))
        return FakeQuery(self.response)


@pytest.mark.asyncio
async def test_authorized_admin_is_true() -> None:
    client = FakeClient(FakeResponse([{"authorize_admin_order_review": True}]))

    result = await SupabaseAdminAuthorizationRepository(client).authorize(123, "PRIMARY")

    assert result is True
    assert client.calls == [
        (
            "authorize_admin_order_review",
            {"p_telegram_user_id": 123, "p_actor_type": "primary"},
        )
    ]


@pytest.mark.asyncio
async def test_denied_admin_is_false() -> None:
    client = FakeClient(FakeResponse([{"authorize_admin_order_review": False}]))

    assert await SupabaseAdminAuthorizationRepository(client).authorize(123, "backup") is False


@pytest.mark.asyncio
async def test_malformed_authorization_response_fails_closed() -> None:
    client = FakeClient(FakeResponse([{"authorize_admin_order_review": "true"}]))

    with pytest.raises(AdminAuthorizationPersistenceError):
        await SupabaseAdminAuthorizationRepository(client).authorize(123, "primary")


@pytest.mark.asyncio
async def test_rpc_error_fails_closed() -> None:
    client = FakeClient(FakeResponse([], error={"message": "database error"}))

    with pytest.raises(AdminAuthorizationPersistenceError):
        await SupabaseAdminAuthorizationRepository(client).authorize(123, "primary")
