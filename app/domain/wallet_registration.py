from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_WALLET_NETWORKS = frozenset({"BEP20", "TRC20"})
MAX_LABEL_LENGTH = 64


@dataclass(frozen=True, slots=True)
class WalletRegistration:
    """Validated customer wallet registration payload."""

    address: str
    network: str
    qr_address: str
    qr_image_file_id: str
    label: str

    def __post_init__(self) -> None:
        address = normalize_wallet_address(self.address)
        network = self.network.strip().upper()
        qr_address = normalize_qr_address(self.qr_address)
        file_id = self.qr_image_file_id.strip()
        label = self.label.strip()

        if network not in SUPPORTED_WALLET_NETWORKS:
            raise ValueError("unsupported wallet network")
        if not address:
            raise ValueError("wallet address is required")
        if not qr_address:
            raise ValueError("qr address is required")
        if address.casefold() != qr_address.casefold():
            raise ValueError("qr address does not match wallet address")
        if not file_id:
            raise ValueError("qr image file id is required")
        if not label or len(label) > MAX_LABEL_LENGTH:
            raise ValueError("wallet label is invalid")

        object.__setattr__(self, "address", address)
        object.__setattr__(self, "network", network)
        object.__setattr__(self, "qr_address", qr_address)
        object.__setattr__(self, "qr_image_file_id", file_id)
        object.__setattr__(self, "label", label)


def normalize_wallet_address(value: str) -> str:
    """Canonicalize user-entered wallet text without changing address semantics."""
    return (value or "").replace(" ", "").strip()


def normalize_qr_address(value: str) -> str:
    """Remove known payment/network URI prefixes before comparison."""
    normalized = normalize_wallet_address(value)
    lowered = normalized.casefold()
    for prefix in ("ethereum:", "tron:", "trc20:", "bep20:", "usdt:"):
        if lowered.startswith(prefix):
            return normalized[len(prefix):].strip()
    return normalized


def validate_wallet_text(address: str, network: str, label: str) -> tuple[str, str, str]:
    normalized_address = normalize_wallet_address(address)
    normalized_network = (network or "").strip().upper()
    normalized_label = (label or "").strip()
    if normalized_network not in SUPPORTED_WALLET_NETWORKS:
        raise ValueError("unsupported wallet network")
    if not normalized_address:
        raise ValueError("wallet address is required")
    if not normalized_label or len(normalized_label) > MAX_LABEL_LENGTH:
        raise ValueError("wallet label is invalid")
    return normalized_address, normalized_network, normalized_label
