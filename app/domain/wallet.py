from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.network import NetworkCode


class WalletStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Wallet:
    wallet_id: UUID
    user_id: int
    network: NetworkCode
    address: str
    status: WalletStatus

    def is_usable_for_order(self) -> bool:
        return self.status is WalletStatus.VERIFIED

    def belongs_to(self, user_id: int) -> bool:
        return self.user_id == user_id
