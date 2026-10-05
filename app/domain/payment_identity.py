from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CustomerPaymentIdentity:
    verified_name: str
    verified_shamcash_account: str

    def __post_init__(self) -> None:
        if not self.verified_name.strip():
            raise ValueError("verified_name is required")
        if not self.verified_shamcash_account.strip():
            raise ValueError("verified_shamcash_account is required")


@dataclass(frozen=True, slots=True)
class AdminPaymentAccountSnapshot:
    account_name: str
    account_number: str
    qr_image_file_id: str

    def __post_init__(self) -> None:
        if not self.account_name.strip():
            raise ValueError("account_name is required")
        if not self.account_number.strip():
            raise ValueError("account_number is required")
        if not self.qr_image_file_id.strip():
            raise ValueError("qr_image_file_id is required")
