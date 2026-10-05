"""Admin customer identity review Telegram handler."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_message, require_private_message


import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramAdminIdentityReviewResponse:
    ok: bool
    message: str
    submissions: list[Any] | None = None


class TelegramAdminCustomerIdentityHandler:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def list_pending(
        self, admin_user_id: int, actor_type: str = "primary"
    ) -> TelegramAdminIdentityReviewResponse:
        if admin_user_id <= 0:
            return TelegramAdminIdentityReviewResponse(False, msg.ADMIN_IDENTITY_CHECK_FAILED)
        try:
            submissions = await self._service.list_pending(admin_user_id, actor_type)
            return TelegramAdminIdentityReviewResponse(True, "", submissions or [])
        except (PermissionError, LookupError):
            return TelegramAdminIdentityReviewResponse(False, msg.ADMIN_UNAUTHORIZED)
        except Exception as exc:
            logger.error("Error in list_pending: %s", exc, exc_info=True)
            return TelegramAdminIdentityReviewResponse(False, msg.ADMIN_ACTION_FAILED)


def build_admin_identity_review_router(
    handler: TelegramAdminCustomerIdentityHandler,
) -> Router:
    router = Router(name="admin-identity-review")

    @router.message(Command("identity_pending"))
    @require_private_message(msg.ADMIN_PRIVATE_ONLY)
    async def identity_pending_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        response = await handler.list_pending(user_id)
        if not response.ok:
            await message.answer(msg.safe(response.message, msg.ADMIN_ACTION_FAILED))
            return
        if not response.submissions:
            await message.answer(msg.ADMIN_NO_PENDING_IDENTITY)
            return
        lines = ["👥 طلبات التحقق المعلقة", ""]
        for sub in response.submissions:
            lines.append(f"• المستخدم: {getattr(sub, 'telegram_user_id', '?')}")
        await message.answer("\n".join(lines))

    return router
