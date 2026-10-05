"""Admin order closure Telegram handler."""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, require_private_callback

CLOSURE_CALLBACK = re.compile(
    r"^admin:closure:(cancel|expire):([0-9a-fA-F-]{36}):(\d+)$"
)


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderClosureInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    action: str  # cancel | expire
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderClosureResponse:
    ok: bool
    message: str
    replayed: bool = False


class TelegramAdminOrderClosureHandler:
    def __init__(self, service: object) -> None:
        self._service = service

    async def handle(self, data: TelegramAdminOrderClosureInput) -> TelegramAdminOrderClosureResponse:
        if data.admin_user_id <= 0 or data.action not in {"cancel", "expire"}:
            return TelegramAdminOrderClosureResponse(False, msg.ADMIN_ACTION_FAILED)
        try:
            method = getattr(self._service, data.action)
            result = await method(
                internal_order_id=data.order_id,
                expected_version=data.expected_version,
                admin_telegram_user_id=data.admin_user_id,
                actor_type=data.actor_type,
                idempotency_key=data.idempotency_key,
            )
            return TelegramAdminOrderClosureResponse(
                True,
                msg.ADMIN_ACTION_SUCCESS,
                replayed=getattr(result, "replayed", False),
            )
        except (PermissionError, LookupError):
            return TelegramAdminOrderClosureResponse(False, msg.ADMIN_UNAUTHORIZED)
        except ValueError:
            return TelegramAdminOrderClosureResponse(False, msg.ADMIN_ACTION_STALE)
        except Exception:
            return TelegramAdminOrderClosureResponse(False, msg.ADMIN_ACTION_FAILED)


def closure_action_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚫 إلغاء الطلب",
                callback_data=f"admin:closure:cancel:{order_id}:{expected_version}",
            ),
            InlineKeyboardButton(
                text="⏰ إنهاء الصلاحية",
                callback_data=f"admin:closure:expire:{order_id}:{expected_version}",
            ),
        ]
    ])


def build_admin_order_closure_router(handler: TelegramAdminOrderClosureHandler) -> Router:
    router = Router(name="admin-order-closure")

    @router.callback_query(F.data.regexp(CLOSURE_CALLBACK.pattern))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def handle_closure(query: CallbackQuery) -> None:
        match = CLOSURE_CALLBACK.fullmatch(query.data or "")
        if match is None:
            await query.answer("طلب غير صالح.", show_alert=True)
            return
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        action, order_id_str, version_str = match.group(1), match.group(2), match.group(3)
        try:
            order_id = UUID(order_id_str)
            expected_version = int(version_str)
        except ValueError:
            await query.answer("بيانات الطلب غير صالحة.", show_alert=True)
            return
        request = TelegramAdminOrderClosureInput(
            admin_user_id=user_id,
            actor_type="primary",
            order_id=order_id,
            expected_version=expected_version,
            action=action,
            idempotency_key=str(uuid4()),
        )
        response = await handler.handle(request)
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok and not response.replayed:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    return router
