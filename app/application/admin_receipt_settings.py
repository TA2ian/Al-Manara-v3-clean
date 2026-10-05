from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AdminReceiptSettingsView:
    deadline_minutes: int


@dataclass(frozen=True, slots=True)
class GetAdminReceiptSettingsCommand:
    admin_user_id: int
    actor_type: str


@dataclass(frozen=True, slots=True)
class UpdateAdminReceiptSettingsCommand:
    admin_user_id: int
    actor_type: str
    deadline_minutes: int


class AdminReceiptSettingsRepository(Protocol):
    async def get_settings(self, admin_telegram_user_id: int) -> AdminReceiptSettingsView: ...

    async def update_settings(self, admin_telegram_user_id: int, deadline_minutes: int) -> bool: ...


class AdminReceiptSettingsService:
    def __init__(self, repository: AdminReceiptSettingsRepository) -> None:
        self._repository = repository

    async def get(self, command: GetAdminReceiptSettingsCommand) -> AdminReceiptSettingsView:
        if not isinstance(command.admin_user_id, int) or command.admin_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        return await self._repository.get_settings(command.admin_user_id)

    async def update(self, command: UpdateAdminReceiptSettingsCommand) -> bool:
        if not isinstance(command.admin_user_id, int) or command.admin_user_id <= 0:
            raise ValueError("administrator identity must be positive")
        if command.actor_type != "primary":
            raise PermissionError("only primary admins can change settings")
            
        if not isinstance(command.deadline_minutes, int):
            raise ValueError("deadline minutes must be an integer")
        if command.deadline_minutes < 1 or command.deadline_minutes > 90:
            raise ValueError("مهلة الإيصال يجب أن تكون بين 1 و 90 دقيقة")
            
        return await self._repository.update_settings(command.admin_user_id, command.deadline_minutes)
