from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class UserState:
    telegram_id: int
    language_code: str = "ar"
    suspended_until: Any = None
    is_disabled: bool = False


class UserRepository(Protocol):
    async def get_or_create_user(
        self, telegram_id: int, username: str | None = None, language_code: str = "ar"
    ) -> UserState: ...
    async def record_misconduct(self, telegram_user_id: int) -> None: ...
    async def get_language(self, telegram_user_id: int) -> str: ...
    async def set_language(self, telegram_user_id: int, language_code: str) -> None: ...
    async def get_all_user_telegram_ids(self) -> list[int]: ...


class UserManagementService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def get_or_create_user(
        self, telegram_id: int, username: str | None = None, language_code: str = "ar"
    ) -> UserState:
        return await self._users.get_or_create_user(telegram_id, username, language_code)

    async def record_misconduct(self, telegram_user_id: int) -> None:
        await self._users.record_misconduct(telegram_user_id)
        
    async def get_language(self, telegram_user_id: int) -> str:
        return await self._users.get_language(telegram_user_id)
        
    async def set_language(self, telegram_user_id: int, language_code: str) -> None:
        await self._users.set_language(telegram_user_id, language_code)
        
    async def get_all_user_telegram_ids(self) -> list[int]:
        return await self._users.get_all_user_telegram_ids()
