from decimal import Decimal

import pytest

from app.domain.currency import CurrencyCode
from app.domain.network import NetworkCode
from app.infrastructure.persistence.order_support_repositories import (
    OrderSupportPersistenceError,
    SupabaseCustomerRepository,
    SupabaseNetworkOrderRepository,
    SupabasePaymentSettingsRepository,
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
async def test_customer_repository_maps_verified_identity():
    client = FakeClient(
        {"get_customer_payment_identity": FakeResponse([{
            "verified_name": "Customer",
            "verified_shamcash_account": "SC-1",
        }])}
    )

    result = await SupabaseCustomerRepository(client).get_payment_identity(123)

    assert result is not None
    assert result.verified_name == "Customer"
    assert result.verified_shamcash_account == "SC-1"
    assert client.calls == [("get_customer_payment_identity", {"p_telegram_user_id": 123})]


@pytest.mark.asyncio
async def test_payment_settings_repository_maps_account():
    client = FakeClient(
        {"get_admin_payment_account": FakeResponse([{
            "account_name": "Admin",
            "account_number": "ACC-1",
            "qr_image_file_id": "QR-1",
        }])}
    )

    result = await SupabasePaymentSettingsRepository(client).get_admin_payment_account(CurrencyCode.USD)

    assert result is not None
    assert result.account_name == "Admin"
    assert result.account_number == "ACC-1"
    assert result.qr_image_file_id == "QR-1"
    assert client.calls == [("get_admin_payment_account", {"p_currency": "USD"})]


@pytest.mark.asyncio
async def test_network_repository_maps_decimal_bounds():
    client = FakeClient(
        {"get_network_config": FakeResponse([{
            "code": "BEP20",
            "display_name": "BEP20",
            "enabled": True,
            "address_regex": r"^0x[0-9A-Fa-f]{40}$",
            "requires_memo": False,
            "min_amount": "0.001",
            "max_amount": "1000000",
        }])}
    )

    result = await SupabaseNetworkOrderRepository(client).get_enabled(" bep20 ")

    assert result is not None
    assert result.code is NetworkCode.BEP20
    assert result.enabled is True
    assert result.min_amount == Decimal("0.001")
    assert result.max_amount == Decimal("1000000")


@pytest.mark.asyncio
async def test_repository_rejects_malformed_network_payload():
    client = FakeClient(
        {"get_network_config": FakeResponse([{
            "code": "BEP20",
            "display_name": "BEP20",
            "enabled": True,
            "address_regex": ".*",
            "requires_memo": False,
            "min_amount": "not-a-number",
            "max_amount": "100",
        }])}
    )

    with pytest.raises(OrderSupportPersistenceError, match="invalid network config payload"):
        await SupabaseNetworkOrderRepository(client).get_enabled("BEP20")
