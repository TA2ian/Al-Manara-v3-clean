from decimal import Decimal

import pytest

from app.domain.money import MoneyError, OrderFinancials


def test_dual_fees_are_separate_and_reduce_only_net_fulfillment() -> None:
    financials = OrderFinancials.calculate(
        requested_amount=Decimal("100"),
        fee_percent=Decimal("2.5"),
        network_fixed_fee_usdt=Decimal("1.25"),
        payment_currency="USD",
        exchange_rate=None,
        rounding_policy_version="v1",
    )

    assert financials.fee_amount == Decimal("2.500")
    assert financials.network_fixed_fee_usdt == Decimal("1.250")
    assert financials.total_fee_usdt == Decimal("3.750")
    assert financials.net_usdt_amount == Decimal("96.250")
    assert financials.local_amount == Decimal("100.00")


def test_fixed_network_fee_cannot_consume_customer_amount() -> None:
    with pytest.raises(MoneyError, match="net_usdt_amount"):
        OrderFinancials.calculate(
            requested_amount=Decimal("1"),
            fee_percent=Decimal("0"),
            network_fixed_fee_usdt=Decimal("1"),
            payment_currency="USD",
            exchange_rate=None,
            rounding_policy_version="v1",
        )
