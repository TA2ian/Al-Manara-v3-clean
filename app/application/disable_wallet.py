from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
from uuid import UUID

from app.application.wallet_ports import WalletRepository
from app.domain.wallet import WalletStatus


DISABLE_WALLET_WARNING = (
    "تعطيل هذه المحفظة إجراء غير قابل للتراجع. "
    "لن تُحذف المحفظة أو سجل العمليات المرتبط بها، "
    "لكن لن يمكن استخدامها لإنشاء طلبات جديدة."
)


@dataclass(frozen=True, slots=True)
class DisableWalletCommand:
    wallet_id: UUID
    user_id: int
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class DisableWalletResult:
    disabled: bool
    confirmation_required: bool
    message: str


class AuditLogger(Protocol):
    async def record(
        self,
        event: str,
        *,
        actor_user_id: int,
        target_id: UUID,
        metadata: Mapping[str, object],
    ) -> None: ...


class DisableWalletService:
    """Application workflow for the irreversible wallet disable operation."""

    def __init__(self, wallets: WalletRepository, audit: AuditLogger) -> None:
        self._wallets = wallets
        self._audit = audit

    async def execute(self, command: DisableWalletCommand) -> DisableWalletResult:
        wallet = await self._wallets.get_for_user(command.wallet_id, command.user_id)
        if wallet is None:
            raise LookupError("wallet not found for customer")

        if wallet.status is WalletStatus.DISABLED:
            return DisableWalletResult(False, False, "wallet is already disabled")

        if wallet.status is not WalletStatus.VERIFIED:
            raise ValueError("only a verified wallet can be disabled")

        if not command.confirmed:
            return DisableWalletResult(False, True, DISABLE_WALLET_WARNING)

        changed = await self._wallets.disable_verified_for_user(
            command.wallet_id,
            command.user_id,
        )
        if not changed:
            raise RuntimeError("wallet could not be disabled")

        await self._audit.record(
            "wallet_disabled",
            actor_user_id=command.user_id,
            target_id=command.wallet_id,
            metadata={"wallet_status": WalletStatus.DISABLED.value},
        )
        return DisableWalletResult(True, False, "wallet disabled")
