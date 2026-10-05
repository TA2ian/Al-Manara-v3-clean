import pytest

from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity


def test_customer_payment_identity_requires_both_fields() -> None:
    identity = CustomerPaymentIdentity("Customer", "0999999999")
    assert identity.verified_name == "Customer"
    assert identity.verified_shamcash_account == "0999999999"

    with pytest.raises(ValueError):
        CustomerPaymentIdentity("", "0999999999")
    with pytest.raises(ValueError):
        CustomerPaymentIdentity("Customer", "")


def test_admin_payment_account_snapshot_requires_qr_file_id() -> None:
    account = AdminPaymentAccountSnapshot("Admin", "0888888888", "telegram-file-id")
    assert account.qr_image_file_id == "telegram-file-id"

    with pytest.raises(ValueError):
        AdminPaymentAccountSnapshot("Admin", "0888888888", "")
