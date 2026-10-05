from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.wallet import Wallet


class WalletRepository(Protocol):
    async def get_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None: ...

    async def get_verified_for_user(self, wallet_id: UUID, user_id: int) -> Wallet | None: ...

    async def list_verified_for_user(self, user_id: int) -> tuple[Wallet, ...]: ...

    async def find_verified_by_address(self, address: str) -> Wallet | None: ...

    async def create_pending(
        self,
        *,
        user_id: int,
        address: str,
        network: str,
        qr_image_file_id: str,
        label: str,
    ) -> Wallet: ...

    async def disable_verified_for_user(self, wallet_id: UUID, user_id: int) -> bool: ...


class NetworkConfigRepository(Protocol):
    async def get_enabled(self, code: str): ...
