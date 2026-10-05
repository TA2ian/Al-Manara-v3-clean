from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import re


class NetworkCode(StrEnum):
    BEP20 = "BEP20"
    TRC20 = "TRC20"
    TON = "TON"
    ARB = "ARB"
    ETH = "ETH"
    SOL = "SOL"


@dataclass(frozen=True, slots=True)
class NetworkConfig:
    code: NetworkCode
    display_name: str
    enabled: bool
    address_regex: str
    requires_memo: bool
    min_amount: Decimal
    max_amount: Decimal


NETWORKS: tuple[NetworkConfig, ...] = (
    NetworkConfig(NetworkCode.BEP20, "BEP20", True, r"^0x[0-9a-fA-F]{40}$", False, Decimal("1"), Decimal("100000")),
    NetworkConfig(NetworkCode.TRC20, "TRC20", True, r"^T[1-9A-HJ-NP-Za-km-z]{33}$", False, Decimal("1"), Decimal("100000")),
    NetworkConfig(NetworkCode.TON, "TON", False, r".+", True, Decimal("0.001"), Decimal("0.001")),
    NetworkConfig(NetworkCode.ARB, "ARB", False, r"^0x[0-9a-fA-F]{40}$", False, Decimal("0.001"), Decimal("0.001")),
    NetworkConfig(NetworkCode.ETH, "ETH", False, r"^0x[0-9a-fA-F]{40}$", False, Decimal("0.001"), Decimal("0.001")),
    NetworkConfig(NetworkCode.SOL, "SOL", False, r".+", False, Decimal("0.001"), Decimal("0.001")),
)


_NETWORK_ALIASES: dict[str, NetworkCode] = {
    "BEP20": NetworkCode.BEP20,
    "BEP-20": NetworkCode.BEP20,
    "BNB SMART CHAIN": NetworkCode.BEP20,
    "TRC20": NetworkCode.TRC20,
    "TRC-20": NetworkCode.TRC20,
    "TRON": NetworkCode.TRC20,
    "TON": NetworkCode.TON,
    "ARBITRUM": NetworkCode.ARB,
    "ARB": NetworkCode.ARB,
    "ETH": NetworkCode.ETH,
    "ETHEREUM": NetworkCode.ETH,
    "SOL": NetworkCode.SOL,
    "SOLANA": NetworkCode.SOL,
}


def normalize_network(raw: str) -> NetworkCode | None:
    normalized = " ".join(raw.strip().upper().split())
    return _NETWORK_ALIASES.get(normalized)


def get_network(code: NetworkCode) -> NetworkConfig:
    for network in NETWORKS:
        if network.code is code:
            return network
    raise ValueError(f"unsupported network: {code}")


def validate_network_address(network: NetworkConfig, address: str) -> str:
    normalized = address.strip()
    if not network.enabled:
        raise ValueError(f"network is disabled: {network.code.value}")
    if not re.fullmatch(network.address_regex, normalized):
        raise ValueError(f"invalid {network.code.value} address")
    return normalized


def validate_amount(network: NetworkConfig, amount: Decimal) -> Decimal:
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be positive and finite")
    if amount < network.min_amount or amount > network.max_amount:
        raise ValueError("amount is outside network limits")
    return amount
