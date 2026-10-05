from decimal import Decimal

import pytest

from app.domain.money import MoneyError, OrderFinancials


POLICY = "ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001"


def test_fee_is_deducted_from_requested_usdt() -> None:
    financials = OrderFinancials.calculate(
        Decimal("100"), Decimal("10"), "USD", None, POLICY
    )

    assert financials.requested_amount == Decimal("100.000")
    assert financials.fee_amount == Decimal("10.000")
    assert financials.net_usdt_amount == Decimal("90.000")
    assert financials.local_amount == Decimal("100.00")


def test_syp_local_amount_does_not_include_fee() -> None:
    financials = OrderFinancials.calculate(
        Decimal("100"), Decimal("10"), "NEW.SYP", Decimal("135"), POLICY
    )

    assert financials.fee_amount == Decimal("10.000")
    assert financials.net_usdt_amount == Decimal("90.000")
    assert financials.local_amount == Decimal("13500.00")


def test_rounding_is_half_up() -> None:
    financials = OrderFinancials.calculate(
        Decimal("1.005"), Decimal("10"), "USD", None, POLICY
    )

    assert financials.requested_amount == Decimal("1.005")
    assert financials.fee_amount == Decimal("0.101")
    assert financials.net_usdt_amount == Decimal("0.904")


def test_usd_rejects_exchange_rate() -> None:
    with pytest.raises(MoneyError, match="must not use an exchange rate"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), "USD", Decimal("135"), POLICY
        )


def test_new_syp_requires_positive_exchange_rate() -> None:
    with pytest.raises(MoneyError, match="requires a positive exchange rate"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("5"), "NEW.SYP", None, POLICY
        )


def test_fee_cannot_reduce_net_amount_to_zero() -> None:
    with pytest.raises(MoneyError, match=r"fee_percent must be in \[0, 100\)"):
        OrderFinancials.calculate(
            Decimal("10"), Decimal("100"), "USD", None, POLICY
        )
