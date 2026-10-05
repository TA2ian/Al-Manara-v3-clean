"""Admin order review Telegram handler — approve / reject / request clarification with smart rejection templates, previews, and user notifications."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramAPIError

from app.runtime.telegram.admin.rejection_templates import (
    build_clarification_explanation,
    build_rejection_explanation,
)
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, require_private_callback

logger = logging.getLogger(__name__)

REVIEW_CALLBACK = re.compile(
    r"^admin:review:(approve|reject|clarify):([0-9a-fA-F-]{36}):(\d+)$"
)

REJECT_CONFIRM_CALLBACK = "admin:review:reject_confirm"
REJECT_CUSTOM_CALLBACK = "admin:review:reject_custom"
REJECT_CANCEL_CALLBACK = "admin:review:reject_cancel"


class RejectionReviewStates(StatesGroup):
    waiting_for_custom_reason = State()


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderReviewInput:
    admin_user_id: int
    actor_type: str
    order_id: UUID
    expected_version: int
    action: str  # approve | reject | clarify
    reason: str | None = None
    idempotency_key: str = ""


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderReviewResponse:
    ok: bool
    message: str
    version: int | None = None
    replayed: bool = False


class TelegramAdminOrderReviewHandler:
    """Adapter between Telegram and AdminOrderReviewService."""

    def __init__(self, service: object) -> None:
        self._service = service

    async def handle(self, data: TelegramAdminOrderReviewInput) -> TelegramAdminOrderReviewResponse:
        if (
            data.admin_user_id <= 0
            or data.action not in {"approve", "reject", "clarify"}
            or data.expected_version < 1
        ):
            return TelegramAdminOrderReviewResponse(False, msg.ADMIN_ACTION_FAILED)
        try:
            method = getattr(self._service, data.action)
            kwargs = {
                "internal_order_id": data.order_id,
                "expected_version": data.expected_version,
                "admin_telegram_user_id": data.admin_user_id,
                "actor_type": data.actor_type,
                "idempotency_key": data.idempotency_key,
            }
            if data.reason is not None and data.action in {"reject", "clarify"}:
                kwargs["reason"] = data.reason
            result = await method(**kwargs)
            return TelegramAdminOrderReviewResponse(
                True,
                msg.ADMIN_ACTION_SUCCESS,
                version=getattr(result, "version", None),
                replayed=getattr(result, "replayed", False),
            )
        except (PermissionError, LookupError):
            return TelegramAdminOrderReviewResponse(False, msg.ADMIN_UNAUTHORIZED)
        except ValueError:
            return TelegramAdminOrderReviewResponse(False, msg.ADMIN_ACTION_STALE)
        except Exception:
            return TelegramAdminOrderReviewResponse(False, msg.ADMIN_ACTION_FAILED)


def order_action_markup(order_id: UUID, expected_version: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ موافقة",
                callback_data=f"admin:review:approve:{order_id}:{expected_version}",
            ),
            InlineKeyboardButton(
                text="❌ رفض الإيصال",
                callback_data=f"admin:review:reject:{order_id}:{expected_version}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="❓ طلب توضيح",
                callback_data=f"admin:review:clarify:{order_id}:{expected_version}",
            )
        ],
    ])


def rejection_preview_markup(order_id: UUID, expected_version: int, action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ إرسال التوضيح والاعتماد",
                callback_data=f"{REJECT_CONFIRM_CALLBACK}:{action}:{order_id}:{expected_version}",
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ تعديل النص يدوياً",
                callback_data=f"{REJECT_CUSTOM_CALLBACK}:{action}:{order_id}:{expected_version}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ إلغاء العملية",
                callback_data=REJECT_CANCEL_CALLBACK,
            )
        ]
    ])


def build_admin_order_review_router(handler: TelegramAdminOrderReviewHandler) -> Router:
    router = Router(name="admin-order-review")

    async def _notify_customer(bot: Any, target_telegram_id: int | None, text: str) -> None:
        if not target_telegram_id:
            return
        try:
            await bot.send_message(target_telegram_id, text)
        except TelegramAPIError as exc:
            logger.warning(f"Failed to send review update notification to customer {target_telegram_id}: {exc}")

    @router.callback_query(F.data == REJECT_CANCEL_CALLBACK)
    async def cancel_rejection(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await query.answer("تم إلغاء العملية.")
        try:
            await query.message.edit_text("تم إلغاء عملية الرفض والتراجع.")
        except Exception:
            pass

    @router.callback_query(F.data.regexp(REVIEW_CALLBACK.pattern))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def handle_review(query: CallbackQuery, state: FSMContext) -> None:
        match = REVIEW_CALLBACK.fullmatch(query.data or "")
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

        # 1. Approval flow (Direct Execution & Customer Notification)
        if action == "approve":
            request = TelegramAdminOrderReviewInput(
                admin_user_id=user_id,
                actor_type="primary",
                order_id=order_id,
                expected_version=expected_version,
                action="approve",
                idempotency_key=str(uuid4()),
            )
            response = await handler.handle(request)
            await query.answer(response.message, show_alert=not response.ok)
            if response.ok and not response.replayed:
                try:
                    await query.message.edit_reply_markup(reply_markup=None)
                    await query.message.answer(f"✅ تم القبول والاعتماد بنجاح للطلب ({order_id_str[:8]}).")
                except Exception:
                    pass
            return

        # 2. Reject or Clarify -> Auto-generate Arabic Explanation Template & Preview Modal!
        auto_reason = (
            build_rejection_explanation("amount_mismatch")
            if action == "reject"
            else build_clarification_explanation("ocr_confidence_below_threshold")
        )

        await state.update_data(
            review_action=action,
            review_order_id=order_id_str,
            review_version=expected_version,
            pending_explanation=auto_reason,
            admin_user_id=user_id,
        )

        action_title = "رفض الإيصال" if action == "reject" else "طلب توضيح"
        await query.answer()
        await query.message.answer(
            f"📝 **معاينة نموذج {action_title} المقترح للعميل**\n\n"
            f"الرسالة التي ستصل للعميل:\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"\"{auto_reason}\"\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"هل تريد إرسال هذا التوضيح كـ نموذج، أم تعديله يدوياً؟",
            reply_markup=rejection_preview_markup(order_id, expected_version, action),
        )

    # 3. Confirm Template Dispatch
    @router.callback_query(F.data.startswith(REJECT_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def confirm_rejection_dispatch(query: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("admin_user_id") or await get_user_id_from_callback(query)
        action = data.get("review_action") or "reject"
        explanation = data.get("pending_explanation") or "تم رفض الطلب لعدم استيفاء البيانات."
        order_id_str = data.get("review_order_id")
        version = data.get("review_version")

        if not order_id_str or not version or not user_id:
            await state.clear()
            await query.answer(msg.GENERIC_ERROR, show_alert=True)
            return

        request = TelegramAdminOrderReviewInput(
            admin_user_id=user_id,
            actor_type="primary",
            order_id=UUID(order_id_str),
            expected_version=version,
            action=action,
            reason=explanation,
            idempotency_key=str(uuid4()),
        )
        response = await handler.handle(request)
        await state.clear()
        await query.answer(response.message, show_alert=not response.ok)

        if response.ok:
            action_label = "تم الرفض" if action == "reject" else "تم طلب التوضيح"
            await query.message.edit_text(
                f"✅ {action_label} بنجاح للطلب (`{order_id_str[:8]}`) وتم إرسال التوضيح التالي للعميل:\n\n\"{explanation}\""
            )

    def cancel_only_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ إلغاء العملية", callback_data=REJECT_CANCEL_CALLBACK)]
        ])

    # 4. Custom Reason Text Entry
    @router.callback_query(F.data.startswith(REJECT_CUSTOM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def prompt_custom_reason(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(RejectionReviewStates.waiting_for_custom_reason)
        await query.answer()
        await query.message.answer("✏️ أرسل نص التوضيح/السبب المخصص الذي تريد إرساله للعميل:", reply_markup=cancel_only_markup())

    @router.message(RejectionReviewStates.waiting_for_custom_reason)
    async def process_custom_reason(message: Message, state: FSMContext) -> None:
        custom_reason = (message.text or "").strip()
        if not custom_reason or len(custom_reason) < 3:
            await message.answer("يرجى كتابة نص توضيح واضح (3 حروف على الأقل).", reply_markup=cancel_only_markup())
            return

        await state.update_data(pending_explanation=custom_reason)
        data = await state.get_data()
        order_id_str = data.get("review_order_id", "")
        version = data.get("review_version", 1)
        action = data.get("review_action", "reject")

        # Show updated preview card with custom text
        await message.answer(
            f"📝 **معاينة التوضيح المخصص قبل الإرسال**\n\n"
            f"الرسالة التي ستصل للعميل:\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"\"{custom_reason}\"\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"هل تريد إرسال هذه الرسالة واعتمد الإجراء؟",
            reply_markup=rejection_preview_markup(UUID(order_id_str), version, action),
        )

    return router
