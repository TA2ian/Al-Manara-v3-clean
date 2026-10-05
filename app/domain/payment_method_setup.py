from __future__ import annotations

from dataclasses import dataclass


MIN_RECIPIENT_NAME_LENGTH = 2
MAX_RECIPIENT_NAME_LENGTH = 100
MIN_RECEIVING_ADDRESS_LENGTH = 5
MAX_RECEIVING_ADDRESS_LENGTH = 150


@dataclass(frozen=True, slots=True)
class PaymentMethodSetup:
    """Validated administrator-facing receiving-account configuration."""

    recipient_name: str
    receiving_address: str
    qr_address: str
    qr_image_file_id: str

    def __post_init__(self) -> None:
        recipient = self.recipient_name.strip()
        address = normalize_receiving_address(self.receiving_address)
        qr_address = normalize_receiving_address(self.qr_address)
        file_id = self.qr_image_file_id.strip()

        if not MIN_RECIPIENT_NAME_LENGTH <= len(recipient) <= MAX_RECIPIENT_NAME_LENGTH:
            raise ValueError("recipient name length is invalid")
        if not MIN_RECEIVING_ADDRESS_LENGTH <= len(address) <= MAX_RECEIVING_ADDRESS_LENGTH:
            raise ValueError("receiving address length is invalid")
        if not qr_address:
            raise ValueError("qr address is required")
        if address.casefold() != qr_address.casefold():
            raise ValueError("qr address does not match receiving address")
        if not file_id:
            raise ValueError("qr image file id is required")

        object.__setattr__(self, "recipient_name", recipient)
        object.__setattr__(self, "receiving_address", address)
        object.__setattr__(self, "qr_address", qr_address)
        object.__setattr__(self, "qr_image_file_id", file_id)


def normalize_receiving_address(value: str) -> str:
    """Normalize supported ShamCash URI prefixes without altering the address itself."""
    normalized = (value or "").strip()
    lowered = normalized.casefold()
    for prefix in ("shamcash://", "shamcash:"):
        if lowered.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def validate_payment_method_text(*, recipient_name: str, receiving_address: str) -> tuple[str, str]:
    recipient = (recipient_name or "").strip()
    address = normalize_receiving_address(receiving_address)
    if not MIN_RECIPIENT_NAME_LENGTH <= len(recipient) <= MAX_RECIPIENT_NAME_LENGTH:
        raise ValueError("recipient name length is invalid")
    if not MIN_RECEIVING_ADDRESS_LENGTH <= len(address) <= MAX_RECEIVING_ADDRESS_LENGTH:
        raise ValueError("receiving address length is invalid")
    return recipient, address
