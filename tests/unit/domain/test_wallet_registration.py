import pytest

from app.domain.wallet_registration import (
    WalletRegistration,
    normalize_qr_address,
    normalize_wallet_address,
    validate_wallet_text,
)


def test_normalize_qr_address_removes_known_prefixes() -> None:
    assert normalize_qr_address("ethereum:0xabc") == "0xabc"
    assert normalize_qr_address("TRON:T123") == "T123"
    assert normalize_qr_address("  T 123  ") == "T123"


def test_normalize_wallet_address_removes_embedded_spaces() -> None:
    assert normalize_wallet_address(" 0x ab c ") == "0xabc"


def test_validate_wallet_text_accepts_supported_networks() -> None:
    assert validate_wallet_text(" 0x ab c ", "bep20", " Main Wallet ") == (
        "0xabc",
        "BEP20",
        "Main Wallet",
    )


def test_wallet_registration_requires_qr_match_and_file_id() -> None:
    wallet = WalletRegistration("T 123", "TRC20", "tron:T123", "telegram-file", "Main")
    assert wallet.address == "T123"

    with pytest.raises(ValueError, match="does not match"):
        WalletRegistration("T123", "TRC20", "T999", "telegram-file", "Main")

    with pytest.raises(ValueError, match="qr image file id"):
        WalletRegistration("T123", "TRC20", "T123", "", "Main")


def test_wallet_registration_rejects_unsupported_network_and_empty_label() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        WalletRegistration("addr", "TON", "addr", "file", "Main")
    with pytest.raises(ValueError, match="label"):
        WalletRegistration("addr", "BEP20", "addr", "file", "")
