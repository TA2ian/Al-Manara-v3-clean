"""Admin receipt settings Telegram handler."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from app.application.admin_receipt_settings import (
    GetAdminReceiptSettingsCommand,
    UpdateAdminReceiptSettingsCommand,
)
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, require_private_callback, get_user_id_from_message


class AdminReceiptSettingsStates(StatesGroup):
    waiting_for_deadline = State()


class TelegramAdminReceiptSettingsHandler:
    def __init__(self, settings_service: Any) -> None:
        self._service = settings_service

    async def get_view(self, admin_user_id: int):
        return await self._service.get(GetAdminReceiptSettingsCommand(
            admin_user_id=admin_user_id,
            actor_type="primary"
        ))
        
    async def update(self, admin_user_id: int, deadline: int):
        return await self._service.update(UpdateAdminReceiptSettingsCommand(
            admin_user_id=admin_user_id,
            actor_type="primary",
            deadline_minutes=deadline
        ))


def build_admin_receipt_settings_router(
    handler: TelegramAdminReceiptSettingsHandler,
    identity_handler: Any,
) -> Router:
    router = Router(name="admin-receipt-settings")
    
    async def _authorize(user_id: int) -> Any:
        return await identity_handler.list_pending(user_id)

    def cancel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ إلغاء والتراجع", callback_data="admin:settings:cancel")]
        ])

    @router.callback_query(F.data == "admin:settings:receipt")
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def view_settings(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        try:
            view = await handler.get_view(user_id)
        except Exception:
            await query.answer("تعذر جلب الإعدادات.", show_alert=True)
            return

        await query.answer()
        text = (
            f"⚙️ **إعدادات الإيصالات**\n\n"
            f"المهلة الزمنية الحالية المسموحة لرفع الإيصال: **{view.deadline_minutes} دقيقة**\n\n"
            "هل ترغب بتعديلها؟"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ تعديل المهلة", callback_data="admin:settings:receipt:edit")],
            [InlineKeyboardButton(text="🔙 العودة للوحة التحكم", callback_data="admin:dashboard")],
        ])
        await query.message.edit_text(text, reply_markup=markup)

    @router.callback_query(F.data == "admin:settings:receipt:edit")
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def edit_settings_prompt(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        await state.set_state(AdminReceiptSettingsStates.waiting_for_deadline)
        await query.answer()
        await query.message.edit_text(
            "⏳ أدخل المهلة الزمنية الجديدة بالدقائق (يجب أن تكون بين 1 و 90):",
            reply_markup=cancel_markup()
        )

    @router.message(AdminReceiptSettingsStates.waiting_for_deadline)
    async def process_new_deadline(message: Message, state: FSMContext) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await state.clear()
            await message.answer(msg.ADMIN_UNAUTHORIZED)
            return

        text = message.text.strip()
        if not text.isdigit():
            await message.answer("الرجاء إدخال رقم صحيح.", reply_markup=cancel_markup())
            return
            
        new_deadline = int(text)
        
        try:
            success = await handler.update(user_id, new_deadline)
            await state.clear()
            if success:
                await message.answer(f"✅ تم تحديث المهلة بنجاح لتصبح {new_deadline} دقيقة.")
            else:
                await message.answer(msg.ADMIN_ACTION_FAILED)
        except ValueError as e:
            await message.answer(str(e), reply_markup=cancel_markup())
        except PermissionError as e:
            await state.clear()
            await message.answer(f"❌ {str(e)}")
        except Exception:
            await state.clear()
            await message.answer(msg.ADMIN_ACTION_FAILED)

    @router.callback_query(F.data == "admin:settings:cancel")
    async def cancel_settings_edit(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await view_settings(query)

    return router
