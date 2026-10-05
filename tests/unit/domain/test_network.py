from decimal import Decimal

from app.domain.network import NetworkCode, get_network


def test_network_configuration_contains_no_pricing_policy() -> None:
    network = get_network(NetworkCode.BEP20)
    assert network.code is NetworkCode.BEP20
    assert not hasattr(network, "service_fee_percent")
    assert network.min_amount == Decimal("1")
    assert network.max_amount == Decimal("100000")
