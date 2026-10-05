"""Admin fulfillment Telegram handler — claim and complete delivery."""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.application.fulfillment import FulfillmentService
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, require_private_callback

FULFILLMENT_CALLBACK = re.compile(
    r"^admin:fulfillment:(claim|complete):([0-9a-fA-F-]{36}):(\d+)$"
)


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramFulfillmentResponse:
    ok: bool
    status: str | None
    version: int | None
    replayed: bool
    message: str


class TelegramFulfillmentHandler:
    """Adapter between Telegram and FulfillmentService."""

    def __init__(self, service: FulfillmentService) -> None:
        self._service = service

    async def claim(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="claim")

    async def complete(self, request: TelegramFulfillmentInput) -> TelegramFulfillmentResponse:
        return await self._run(request, operation="complete")

    async def _run(self, request: TelegramFulfillmentInput, operation: str) -> TelegramFulfillmentResponse:
        if (
            request.admin_user_id <= 0
            or request.expected_version < 1
            or not isinstance(request.order_id, UUID)
            or not request.idempotency_key.strip()
        ):
            return TelegramFulfillmentResponse(False, None, None, False, msg.FULFILLMENT_FAILED)
        actor_type = request.actor_type.strip().lower()
        if actor_type not in {"primary", "backup"}:
            return TelegramFulfillmentResponse(False, None, None, False, msg.FULFILLMENT_FAILED)
        try:
            method = self._service.claim if operation == "claim" else self._service.complete
            result = await method(
                internal_order_id=request.order_id,
                expected_version=request.expected_version,
                admin_telegram_user_id=request.admin_user_id,
                actor_type=actor_type,
                idempotency_key=request.idempotency_key,
            )
        except (PermissionError, LookupError, ValueError):
            return TelegramFulfillmentResponse(False, None, None, False, msg.FULFILLMENT_FAILED)
        except Exception:
            return TelegramFulfillmentResponse(False, None, None, False, msg.FULFILLMENT_FAILED)
        return TelegramFulfillmentResponse(
            True, result.status, result.version, result.replayed, msg.FULFILLMENT_SUCCESS
        )


def fulfillment_action_markup(order_id: UUID, expected_version: int, *, claimed: bool = False) -> InlineKeyboardMarkup:
    action = "complete" if claimed else "claim"
    label = "إتمام التسليم" if claimed else "استلام للتنفيذ"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=label,
            callback_data=f"admin:fulfillment:{action}:{order_id}:{expected_version}",
        )
    ]])


def parse_fulfillment_callback(data: str | None) -> tuple[str, UUID, int] | None:
    match = FULFILLMENT_CALLBACK.fullmatch(data or "")
    if match is None:
        return None
    try:
        return match.group(1), UUID(match.group(2)), int(match.group(3))
    except ValueError:
        return None


def build_fulfillment_router(handler: TelegramFulfillmentHandler) -> Router:
    router = Router(name="admin-fulfillment")

    @router.callback_query(F.data.regexp(FULFILLMENT_CALLBACK.pattern))
    @require_private_callback(msg.FULFILLMENT_PRIVATE_ONLY)
    async def handle_fulfillment(query: CallbackQuery) -> None:
        parsed = parse_fulfillment_callback(query.data)
        if parsed is None:
            await query.answer("هذا الطلب غير صالح.", show_alert=True)
            return
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        operation, order_id, expected_version = parsed
        request = TelegramFulfillmentInput(
            admin_user_id=user_id,
            actor_type="primary",
            order_id=order_id,
            expected_version=expected_version,
            idempotency_key=str(uuid4()),
        )
        response = await (handler.claim(request) if operation == "claim" else handler.complete(request))
        await query.answer(response.message, show_alert=not response.ok)
        if response.ok:
            try:
                if operation == "claim" and response.version is not None:
                    await query.message.edit_reply_markup(
                        reply_markup=fulfillment_action_markup(order_id, response.version, claimed=True)
                    )
                else:
                    await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    return router
