from __future__ import annotations

from dataclasses import dataclass

from app.application.wallet_ports import WalletRepository
from app.domain.wallet import WalletStatus


@dataclass(frozen=True, slots=True)
class ListWalletsCommand:
    user_id: int


class ListWalletsService:
    """Application workflow for presenting customer-owned usable wallets."""

    def __init__(self, wallets: WalletRepository) -> None:
        self._wallets = wallets

    async def execute(self, command: ListWalletsCommand):
        if command.user_id <= 0:
            raise ValueError("invalid customer id")
        wallets = await self._wallets.list_verified_for_user(command.user_id)
        return tuple(wallet for wallet in wallets if wallet.status is WalletStatus.VERIFIED)
