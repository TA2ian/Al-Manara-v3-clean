from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.network import NetworkCode, NetworkConfig, validate_amount, validate_network_address
from app.domain.wallet import Wallet


@dataclass(frozen=True, slots=True)
class OrderWalletSelection:
    wallet_id: UUID
    user_id: int
    network: NetworkCode
    address: str


def validate_wallet_for_order(
    wallet: Wallet,
    user_id: int,
    network: NetworkConfig,
    amount,
) -> OrderWalletSelection:
    if not wallet.belongs_to(user_id):
        raise ValueError("wallet does not belong to user")
    if not wallet.is_usable_for_order():
        raise ValueError("wallet is not verified and usable")
    if wallet.network is not network.code:
        raise ValueError("wallet network does not match selected network")
    address = validate_network_address(network, wallet.address)
    validate_amount(network, amount)
    return OrderWalletSelection(wallet.wallet_id, user_id, network.code, address)
