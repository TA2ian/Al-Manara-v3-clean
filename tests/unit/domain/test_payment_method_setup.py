import pytest

from app.domain.payment_method_setup import (
    PaymentMethodSetup,
    normalize_receiving_address,
    validate_payment_method_text,
)


def test_normalize_shamcash_uri_prefixes() -> None:
    assert normalize_receiving_address("shamcash:0999999999") == "0999999999"
    assert normalize_receiving_address("ShamCash://0999999999") == "0999999999"
    assert normalize_receiving_address(" 0999999999 ") == "0999999999"


def test_validate_payment_method_text_enforces_bounds() -> None:
    assert validate_payment_method_text(
        recipient_name=" Admin ", receiving_address=" 0999999999 "
    ) == ("Admin", "0999999999")

    with pytest.raises(ValueError):
        validate_payment_method_text(recipient_name="A", receiving_address="0999999999")
    with pytest.raises(ValueError):
        validate_payment_method_text(recipient_name="Admin", receiving_address="1234")


def test_payment_method_setup_requires_exact_qr_address_match() -> None:
    setup = PaymentMethodSetup("Admin", "0999999999", "shamcash:0999999999", "telegram-file")
    assert setup.receiving_address == "0999999999"
    assert setup.qr_address == "0999999999"

    with pytest.raises(ValueError, match="does not match"):
        PaymentMethodSetup("Admin", "0999999999", "0888888888", "telegram-file")


def test_payment_method_setup_requires_qr_file_id() -> None:
    with pytest.raises(ValueError, match="qr image file id"):
        PaymentMethodSetup("Admin", "0999999999", "0999999999", "")
