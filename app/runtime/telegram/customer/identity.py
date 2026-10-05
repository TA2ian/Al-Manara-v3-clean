"""Customer identity verification Telegram handler."""
from __future__ import annotations

from dataclasses import dataclass
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message


@dataclass(frozen=True, slots=True)
class TelegramCustomerIdentityInput:
    authenticated_telegram_user_id: int


@dataclass(frozen=True, slots=True)
class TelegramCustomerIdentityResponse:
    ok: bool
    message: str
    status: str | None = None


class CustomerIdentityPort:
    """Protocol — implemented by CustomerIdentityService."""
    async def get_status(self, user_id: int) -> TelegramCustomerIdentityResponse: ...


class TelegramCustomerIdentityHandler:
    """Framework-neutral adapter for customer identity queries."""

    def __init__(self, service: CustomerIdentityPort) -> None:
        self._service = service

    async def handle(self, data: TelegramCustomerIdentityInput) -> TelegramCustomerIdentityResponse:
        if data.authenticated_telegram_user_id <= 0:
            return TelegramCustomerIdentityResponse(False, msg.IDENTITY_CHECK_FAILED)
        try:
            status = await self._service.get_status(data.authenticated_telegram_user_id)
            if status == "APPROVED":
                return TelegramCustomerIdentityResponse(True, msg.VERIFY_ALREADY_VERIFIED, status="APPROVED")
            elif status == "PENDING":
                return TelegramCustomerIdentityResponse(True, msg.VERIFY_PENDING, status="PENDING")
            return TelegramCustomerIdentityResponse(True, msg.VERIFY_PROMPT, status=status)
        except Exception:
            return TelegramCustomerIdentityResponse(False, msg.GENERIC_ERROR)


def build_customer_identity_router(handler: TelegramCustomerIdentityHandler) -> Router:
    router = Router(name="customer-identity")

    async def _handle_verify(user_id: int, send_func) -> None:
        response = await handler.handle(TelegramCustomerIdentityInput(user_id))
        await send_func(response.message or msg.VERIFY_PROMPT)

    @router.message(Command("verify"))
    @require_private_message(msg.DASHBOARD_PRIVATE_ONLY)
    async def verify_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        await _handle_verify(user_id, message.answer)

    @router.callback_query(F.data == "customer:verify")
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def verify_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        await query.answer()
        await _handle_verify(user_id, query.message.answer)

    return router
