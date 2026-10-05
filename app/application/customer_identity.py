from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SubmitCustomerIdentityCommand:
    telegram_user_id: int
    full_name: str
    shamcash_account: str
    telegram_contact_phone: str
    qr_image_file_id: str


@dataclass(frozen=True, slots=True)
class CustomerIdentitySubmission:
    submission_id: UUID
    customer_telegram_user_id: int
    full_name: str
    shamcash_account: str
    qr_image_file_id: str
    submitted_at: datetime


class CustomerIdentityRepository(Protocol):
    async def submit(self, command: SubmitCustomerIdentityCommand) -> UUID: ...

    async def list_pending(
        self, admin_telegram_user_id: int, actor_type: str
    ) -> tuple[CustomerIdentitySubmission, ...]: ...

    async def approve(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID
    ) -> None: ...

    async def get_status(self, telegram_user_id: int) -> str | None: ...

    async def reject(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        submission_id: UUID,
        reason: str,
    ) -> None: ...


class CustomerIdentityService:
    def __init__(self, repository: CustomerIdentityRepository) -> None:
        self._repository = repository

    async def submit(self, command: SubmitCustomerIdentityCommand) -> UUID:
        self._validate_submission(command)
        return await self._repository.submit(command)

    async def get_status(self, telegram_user_id: int) -> str | None:
        if not isinstance(telegram_user_id, int) or telegram_user_id <= 0:
            raise ValueError("customer identity is invalid")
        return await self._repository.get_status(telegram_user_id)

    async def list_pending(
        self, admin_telegram_user_id: int, actor_type: str
    ) -> tuple[CustomerIdentitySubmission, ...]:
        self._validate_admin(admin_telegram_user_id, actor_type)
        return await self._repository.list_pending(admin_telegram_user_id, actor_type)

    async def approve(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID
    ) -> None:
        self._validate_admin(admin_telegram_user_id, actor_type)
        self._validate_submission_id(submission_id)
        await self._repository.approve(admin_telegram_user_id, actor_type, submission_id)

    async def reject(
        self,
        admin_telegram_user_id: int,
        actor_type: str,
        submission_id: UUID,
        reason: str,
    ) -> None:
        self._validate_admin(admin_telegram_user_id, actor_type)
        self._validate_submission_id(submission_id)
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValueError("rejection reason is required")
        await self._repository.reject(
            admin_telegram_user_id, actor_type, submission_id, reason.strip()
        )

    @staticmethod
    def _validate_submission(command: SubmitCustomerIdentityCommand) -> None:
        if not isinstance(command.telegram_user_id, int) or command.telegram_user_id <= 0:
            raise ValueError("customer identity is invalid")
        values = (
            (command.full_name, 1, 200),
            (command.shamcash_account, 1, 100),
            (command.telegram_contact_phone, 6, 32),
            (command.qr_image_file_id, 1, 512),
        )
        if any(not isinstance(value, str) or not low <= len(value.strip()) <= high for value, low, high in values):
            raise ValueError("customer identity details are invalid")

    @staticmethod
    def _validate_admin(admin_telegram_user_id: int, actor_type: str) -> None:
        if not isinstance(admin_telegram_user_id, int) or admin_telegram_user_id <= 0:
            raise ValueError("administrator identity is invalid")
        if not isinstance(actor_type, str) or actor_type.strip().lower() != "primary":
            raise ValueError("administrator role is invalid")

    @staticmethod
    def _validate_submission_id(submission_id: UUID) -> None:
        if not isinstance(submission_id, UUID):
            raise ValueError("identity submission is invalid")