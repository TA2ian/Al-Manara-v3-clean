from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.network import NetworkCode, get_network
from app.domain.wallet import Wallet, WalletStatus
from app.domain.wallet_selection import validate_wallet_for_order


def wallet(user_id: int, network: NetworkCode, status: WalletStatus = WalletStatus.VERIFIED) -> Wallet:
    address = "0x" + "a" * 40 if network is NetworkCode.BEP20 else "T" + "a" * 33
    return Wallet(uuid4(), user_id, network, address, status)


def test_verified_owned_wallet_can_be_selected() -> None:
    selected = validate_wallet_for_order(
        wallet(10, NetworkCode.BEP20),
        10,
        get_network(NetworkCode.BEP20),
        Decimal("10"),
    )
    assert selected.user_id == 10
    assert selected.network is NetworkCode.BEP20


def test_other_users_wallet_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not belong"):
        validate_wallet_for_order(
            wallet(10, NetworkCode.BEP20),
            11,
            get_network(NetworkCode.BEP20),
            Decimal("10"),
        )


def test_unverified_wallet_is_rejected() -> None:
    with pytest.raises(ValueError, match="not verified"):
        validate_wallet_for_order(
            wallet(10, NetworkCode.BEP20, WalletStatus.PENDING),
            10,
            get_network(NetworkCode.BEP20),
            Decimal("10"),
        )


def test_disabled_wallet_is_rejected() -> None:
    with pytest.raises(ValueError, match="not verified"):
        validate_wallet_for_order(
            wallet(10, NetworkCode.BEP20, WalletStatus.DISABLED),
            10,
            get_network(NetworkCode.BEP20),
            Decimal("10"),
        )


def test_network_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="network does not match"):
        validate_wallet_for_order(
            wallet(10, NetworkCode.BEP20),
            10,
            get_network(NetworkCode.TRC20),
            Decimal("10"),
        )
