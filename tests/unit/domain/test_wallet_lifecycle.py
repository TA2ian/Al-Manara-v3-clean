import pytest

from app.domain.wallet_lifecycle import (
    DISABLE_WALLET_WARNING,
    WalletDisableConfirmationRequired,
    WalletDisableRequest,
)


def test_wallet_disable_requires_explicit_confirmation() -> None:
    request = WalletDisableRequest(wallet_id="wallet-1", confirmed=False)

    with pytest.raises(WalletDisableConfirmationRequired, match="لا يمكن إعادة تفعيلها"):
        request.require_confirmation()


def test_wallet_disable_confirmation_is_explicit() -> None:
    request = WalletDisableRequest(wallet_id="wallet-1", confirmed=True)

    request.require_confirmation()


def test_warning_is_the_user_facing_contract() -> None:
    assert "تعطيل هذه المحفظة نهائي" in DISABLE_WALLET_WARNING
    assert "إضافة محفظة جديدة" in DISABLE_WALLET_WARNING
