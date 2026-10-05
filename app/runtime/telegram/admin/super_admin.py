"""Super Admin Telegram router — interactive buttons, confirmation modals, edit previews, and user notifications."""
from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramAPIError

from app.application.super_admin_service import SuperAdminService
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import (
    get_user_id_from_callback,
    get_user_id_from_message,
    require_private_callback,
    require_private_message,
)

logger = logging.getLogger(__name__)

# Initial Callbacks
SUPER_ADMIN_RESET_CALLBACK = "admin:order:reset"
SUPER_ADMIN_DELETE_CALLBACK = "admin:order:delete"
SUPER_ADMIN_BYPASS_CALLBACK = "admin:order:bypass"
SUPER_ADMIN_EDIT_CALLBACK = "admin:order:edit"
SUPER_ADMIN_UNSUSPEND_CALLBACK = "admin:user:unsuspend"
SUPER_ADMIN_FORCE_VERIFY_CALLBACK = "admin:user:force_verify"

# Confirmation Confirm Callbacks
SUPER_ADMIN_RESET_CONFIRM_CALLBACK = "admin:order:reset_confirm"
SUPER_ADMIN_DELETE_CONFIRM_CALLBACK = "admin:order:delete_confirm"
SUPER_ADMIN_BYPASS_CONFIRM_CALLBACK = "admin:order:bypass_confirm"
SUPER_ADMIN_UNSUSPEND_CONFIRM_CALLBACK = "admin:user:unsuspend_confirm"
SUPER_ADMIN_FORCE_VERIFY_CONFIRM_CALLBACK = "admin:user:force_verify_confirm"
SUPER_ADMIN_EDIT_CONFIRM_CALLBACK = "admin:order:edit_confirm"
SUPER_ADMIN_CANCEL_CALLBACK = "admin:action:cancel"


class SuperAdminStates(StatesGroup):
    waiting_for_edit_amount = State()


def confirmation_markup(confirm_callback: str, cancel_callback: str = SUPER_ADMIN_CANCEL_CALLBACK) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ نعم، تأكيد العملية", callback_data=confirm_callback),
            InlineKeyboardButton(text="❌ إلغاء والتراجع", callback_data=cancel_callback),
        ]
    ])


def build_super_admin_router(
    super_admin_service: SuperAdminService,
    identity_handler: Any,
) -> Router:
    router = Router(name="super-admin")

    async def _authorize(user_id: int) -> Any:
        # 1. Base admin check
        auth = await identity_handler.list_pending(user_id)
        if not auth.ok:
            return auth
        
        # 2. Super Admin isolation check
        super_admin_id = os.environ.get("SUPER_ADMIN_ID")
        if not super_admin_id or str(user_id) != str(super_admin_id):
            auth.ok = False
            auth.message = "⛔ هذه العملية محصورة للمدير العام (Super Admin) فقط."
        return auth

    async def _notify_user(bot: Any, target_telegram_id: int, text: str) -> None:
        try:
            await bot.send_message(target_telegram_id, text)
        except TelegramAPIError as exc:
            logger.warning(f"Failed to send update notification to user {target_telegram_id}: {exc}")

    # ─── Cancel Action Handler ────────────────────────────────────────────────
    @router.callback_query(F.data == SUPER_ADMIN_CANCEL_CALLBACK)
    async def cancel_action_callback(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await query.answer("تم إلغاء العملية.")
        try:
            await query.message.edit_text("تم إلغاء العملية والتراجع عن التغييرات.")
        except Exception:
            pass

    # ─── 1. Reset Order (Prompt & Confirm) ───────────────────────────────────
    @router.callback_query(F.data.startswith(SUPER_ADMIN_RESET_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_RESET_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def reset_order_prompt(query: CallbackQuery) -> None:
        order_id_str = str(query.data).split(":")[-1]
        await query.answer()
        await query.message.answer(
            f"⚠️ **تأكيد إعادة فتح الطلب**\n\nهل أنت متأكد من إعادة فتح الطلب (`{order_id_str[:8]}`) ونقله إلى حالة بانتظار الدفع (PENDING_PAYMENT) ليتسنى للعميل رفع إيصال جديد؟",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_RESET_CONFIRM_CALLBACK}:{order_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_RESET_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def reset_order_confirm(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        order_id_str = str(query.data).split(":")[-1]
        success = await super_admin_service.reset_order(user_id, order_id_str, target_status="PENDING_PAYMENT")
        await query.answer()
        if success:
            await query.message.edit_text(f"🔄 تم إعادة فتح الطلب (`{order_id_str[:8]}`) ونقله إلى بانتظار الدفع بنجاح.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    # ─── 2. Bypass OCR (Prompt & Confirm) ────────────────────────────────────
    @router.callback_query(F.data.startswith(SUPER_ADMIN_BYPASS_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_BYPASS_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def bypass_ocr_prompt(query: CallbackQuery) -> None:
        order_id_str = str(query.data).split(":")[-1]
        await query.answer()
        await query.message.answer(
            f"⚠️ **تأكيد تخطي الـ OCR للاختبار**\n\nهل أنت متأكد من اعتماد وتخطي الـ OCR للطلب (`{order_id_str[:8]}`)؟",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_BYPASS_CONFIRM_CALLBACK}:{order_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_BYPASS_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def bypass_ocr_confirm(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        order_id_str = str(query.data).split(":")[-1]
        success = await super_admin_service.bypass_ocr_and_approve(user_id, order_id_str)
        await query.answer()
        if success:
            await query.message.edit_text(f"⚡ تم تخطي الـ OCR واعتماد الطلب (`{order_id_str[:8]}`) بنجاح.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    # ─── 3. Delete Order (Prompt & Confirm) ──────────────────────────────────
    @router.callback_query(F.data.startswith(SUPER_ADMIN_DELETE_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_DELETE_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def delete_order_prompt(query: CallbackQuery) -> None:
        order_id_str = str(query.data).split(":")[-1]
        await query.answer()
        await query.message.answer(
            f"⚠️ **تأكيد حذف الطلب نهائياً**\n\nهل أنت تأكد تماماً من حذف الطلب (`{order_id_str[:8]}`) نهائياً من النظام؟ لا يمكن التراجع عن هذا القرار.",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_DELETE_CONFIRM_CALLBACK}:{order_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_DELETE_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def delete_order_confirm(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        order_id_str = str(query.data).split(":")[-1]
        success = await super_admin_service.delete_order(user_id, order_id_str)
        await query.answer()
        if success:
            await query.message.edit_text(f"🗑️ تم حذف الطلب (`{order_id_str[:8]}`) نهائياً.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    # ─── 4. Edit Order Amount (Input -> Comparison Preview -> Confirm) ────────
    def cancel_only_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ إلغاء والتراجع", callback_data=SUPER_ADMIN_CANCEL_CALLBACK)]
        ])

    @router.callback_query(F.data.startswith(SUPER_ADMIN_EDIT_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_EDIT_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def edit_order_callback(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        order_id_str = str(query.data).split(":")[-1]
        await state.update_data(target_order_id=order_id_str, admin_id=user_id)
        await state.set_state(SuperAdminStates.waiting_for_edit_amount)
        await query.answer()
        await query.message.answer(
            f"✏️ أدخل المبلغ الجديد لـ USDT للطلب (`{order_id_str[:8]}`):",
            reply_markup=cancel_only_markup()
        )

    @router.message(SuperAdminStates.waiting_for_edit_amount)
    async def process_edit_amount_input(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id_str = data.get("target_order_id")
        admin_id = data.get("admin_id")
        if not order_id_str or not admin_id:
            await state.clear()
            await message.answer(msg.GENERIC_ERROR)
            return

        try:
            new_amount = Decimal(message.text.strip())
            if not new_amount.is_finite() or new_amount <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            await message.answer("المبلغ المدخل غير صالح. أرسل رقماً موجباً.", reply_markup=cancel_only_markup())
            return

        # Show Comparison Preview Card before applying!
        await state.update_data(pending_new_amount=str(new_amount))
        await message.answer(
            f"📋 **معاينة تعديل المبلغ قبل التثبيت**\n\n"
            f"• الطلب: `{order_id_str[:8]}`\n"
            f"• المبلغ الجديد المطلوب: `{new_amount} USDT`\n\n"
            f"هل تريد تطبيق وتثبيت هذا التعديل رسمياً؟",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_EDIT_CONFIRM_CALLBACK}:{order_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_EDIT_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def confirm_edit_amount(query: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        new_amount_str = data.get("pending_new_amount")
        admin_id = data.get("admin_id") or await get_user_id_from_callback(query)
        order_id_str = str(query.data).split(":")[-1]

        if not new_amount_str or not admin_id:
            await state.clear()
            await query.answer(msg.GENERIC_ERROR, show_alert=True)
            return

        new_amount = Decimal(new_amount_str)
        success = await super_admin_service.edit_order(admin_id, order_id_str, new_amount=new_amount)
        await state.clear()
        await query.answer()
        if success:
            await query.message.edit_text(f"✅ تم تعديل وتثبيت المبلغ الجديد للطلب (`{order_id_str[:8]}`) إلى {new_amount} USDT بنجاح.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    # ─── 5. Unsuspend User (Prompt & Confirm & Notify) ───────────────────────
    @router.callback_query(F.data.startswith(SUPER_ADMIN_UNSUSPEND_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_UNSUSPEND_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def unsuspend_user_prompt(query: CallbackQuery) -> None:
        target_user_id_str = str(query.data).split(":")[-1]
        await query.answer()
        await query.message.answer(
            f"⚠️ **تأكيد فك الحظر**\n\nهل أنت متأكد من فك الحظر وتصفير المخالفات للمستخدم (`{target_user_id_str}`)؟",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_UNSUSPEND_CONFIRM_CALLBACK}:{target_user_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_UNSUSPEND_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def unsuspend_user_confirm(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        target_user_id_str = str(query.data).split(":")[-1]
        try:
            target_user_id = int(target_user_id_str)
        except ValueError:
            await query.answer("معرف المستخدم غير صالح.", show_alert=True)
            return

        success = await super_admin_service.unsuspend_user(user_id, target_user_id)
        await query.answer()
        if success:
            await query.message.edit_text(f"🔓 تم فك الحظر وتصفير المخالفات للمستخدم ({target_user_id}) بنجاح.")
            # Dispatch Notification to Customer
            await _notify_user(query.bot, target_user_id, "🎉 تم رفع الحظر عن حسابك وتصفير المخالفات. يمكنك الآن استخدام البوت بشكل طبيعي.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    # ─── 6. Force Verify User (Prompt & Confirm & Notify) ─────────────────────
    @router.callback_query(F.data.startswith(SUPER_ADMIN_FORCE_VERIFY_CALLBACK) & ~F.data.startswith(SUPER_ADMIN_FORCE_VERIFY_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def force_verify_user_prompt(query: CallbackQuery) -> None:
        target_user_id_str = str(query.data).split(":")[-1]
        await query.answer()
        await query.message.answer(
            f"⚠️ **تأكيد التوثيق المباشر**\n\nهل أنت متأكد من واعتماد توثيق الهوية المباشر للمستخدم (`{target_user_id_str}`)؟",
            reply_markup=confirmation_markup(f"{SUPER_ADMIN_FORCE_VERIFY_CONFIRM_CALLBACK}:{target_user_id_str}"),
        )

    @router.callback_query(F.data.startswith(SUPER_ADMIN_FORCE_VERIFY_CONFIRM_CALLBACK))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def force_verify_user_confirm(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        target_user_id_str = str(query.data).split(":")[-1]
        try:
            target_user_id = int(target_user_id_str)
        except ValueError:
            await query.answer("معرف المستخدم غير صالح.", show_alert=True)
            return

        success = await super_admin_service.force_verify_user(user_id, target_user_id)
        await query.answer()
        if success:
            await query.message.edit_text(f"✅ تم توثيق واعتماد هوية المستخدم ({target_user_id}) مباشرة.")
            # Dispatch Notification to Customer
            await _notify_user(query.bot, target_user_id, "✅ تهانينا! تم توثيق واعتماد هويتك بنجاح. يمكنك الآن البدء بإنشاء طلبات الشراء عبر /buy.")
        else:
            await query.message.edit_text(msg.ADMIN_ACTION_FAILED)

    return router
