from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.wallet_ports import WalletRepository
from app.domain.wallet_registration import WalletRegistration


@dataclass(frozen=True, slots=True)
class RegisterWalletCommand:
    user_id: int
    address: str
    network: str
    qr_address: str
    qr_image_file_id: str
    label: str


@dataclass(frozen=True, slots=True)
class RegisterWalletResult:
    wallet_id: UUID
    status: str


class RegisterWalletService:
    """Register a customer wallet as PENDING for later verification."""

    def __init__(self, wallets: WalletRepository) -> None:
        self._wallets = wallets

    async def execute(self, command: RegisterWalletCommand) -> RegisterWalletResult:
        if command.user_id <= 0:
            raise ValueError("invalid customer id")

        registration = WalletRegistration(
            address=command.address,
            network=command.network,
            qr_address=command.qr_address,
            qr_image_file_id=command.qr_image_file_id,
            label=command.label,
        )
        existing = await self._wallets.find_verified_by_address(registration.address)
        if existing is not None:
            raise ValueError("wallet address is already verified")

        wallet = await self._wallets.create_pending(
            user_id=command.user_id,
            address=registration.address,
            network=registration.network,
            qr_image_file_id=registration.qr_image_file_id,
            label=registration.label,
        )
        return RegisterWalletResult(wallet_id=wallet.wallet_id, status=wallet.status.value)
