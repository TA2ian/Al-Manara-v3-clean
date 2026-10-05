from uuid import uuid4

import pytest

from app.domain.network import NetworkCode
from app.domain.wallet import WalletStatus
from app.infrastructure.persistence.wallet_repository import (
    SupabaseWalletRepository,
    WalletPersistenceError,
)


class FakeQuery:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


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
async def test_get_verified_wallet_maps_telegram_identity_without_confusing_internal_uuid():
    wallet_id = uuid4()
    client = FakeClient(
        {
            "get_wallet_for_telegram_user": FakeResponse(
                [
                    {
                        "wallet_id": str(wallet_id),
                        "telegram_user_id": 12345,
                        "network_code": "BEP20",
                        "address": "0x" + "a" * 40,
                        "status": "VERIFIED",
                    }
                ]
            )
        }
    )
    repository = SupabaseWalletRepository(client)

    wallet = await repository.get_verified_for_user(wallet_id, 12345)

    assert wallet is not None
    assert wallet.wallet_id == wallet_id
    assert wallet.user_id == 12345
    assert wallet.network is NetworkCode.BEP20
    assert wallet.status is WalletStatus.VERIFIED


@pytest.mark.asyncio
async def test_get_verified_wallet_rejects_disabled_wallet():
    wallet_id = uuid4()
    client = FakeClient(
        {
            "get_wallet_for_telegram_user": FakeResponse(
                [
                    {
                        "wallet_id": str(wallet_id),
                        "telegram_user_id": 12345,
                        "network_code": "BEP20",
                        "address": "0x" + "a" * 40,
                        "status": "DISABLED",
                    }
                ]
            )
        }
    )

    wallet = await SupabaseWalletRepository(client).get_verified_for_user(wallet_id, 12345)

    assert wallet is None


@pytest.mark.asyncio
async def test_disable_maps_rpc_boolean():
    wallet_id = uuid4()
    client = FakeClient(
        {"disable_wallet_for_telegram_user": FakeResponse([{"disabled": True}])}
    )

    result = await SupabaseWalletRepository(client).disable_verified_for_user(wallet_id, 12345)

    assert result is True
    assert client.calls[0][0] == "disable_wallet_for_telegram_user"
    assert client.calls[0][1] == {
        "p_wallet_id": str(wallet_id),
        "p_telegram_user_id": 12345,
    }


@pytest.mark.asyncio
async def test_invalid_rpc_payload_is_rejected():
    wallet_id = uuid4()
    client = FakeClient(
        {"disable_wallet_for_telegram_user": FakeResponse([{"disabled": "maybe"}])}
    )

    with pytest.raises(WalletPersistenceError, match="invalid boolean"):
        await SupabaseWalletRepository(client).disable_verified_for_user(wallet_id, 12345)
