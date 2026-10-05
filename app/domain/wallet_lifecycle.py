from __future__ import annotations

from dataclasses import dataclass


DISABLE_WALLET_WARNING = (
    "تعطيل هذه المحفظة نهائي ولا يمكن إعادة تفعيلها لاحقًا. "
    "إذا كنت تريد استخدامها مجددًا، ستحتاج إلى إضافة محفظة جديدة. "
    "هل تريد المتابعة؟"
)


class WalletDisableConfirmationRequired(ValueError):
    """Raised when disabling a wallet has not been explicitly confirmed."""

    def __init__(self) -> None:
        super().__init__(DISABLE_WALLET_WARNING)


@dataclass(frozen=True, slots=True)
class WalletDisableRequest:
    """Explicit customer confirmation required before disabling a wallet."""

    wallet_id: str
    confirmed: bool

    def require_confirmation(self) -> None:
        if not self.confirmed:
            raise WalletDisableConfirmationRequired()
