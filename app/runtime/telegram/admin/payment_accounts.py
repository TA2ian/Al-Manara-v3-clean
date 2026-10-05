"""Admin payment accounts Telegram handler."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.currency import CurrencyCode
from app.domain.payment_method_setup import PaymentMethodSetup
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message


class AdminPaymentAccountStates(StatesGroup):
    waiting_for_account_name = State()
    waiting_for_account_number = State()
    waiting_for_qr_image = State()


class TelegramAdminPaymentAccountHandler:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def list_accounts(self, admin_id: int):
        return await self._service.list(admin_id, "primary")

    async def toggle_active(self, admin_id: int, currency: str, is_active: bool):
        return await self._service.set_active(admin_id, "primary", CurrencyCode(currency), is_active)
        
    async def upsert(self, admin_id: int, currency: str, name: str, number: str, qr_file_id: str):
        setup = PaymentMethodSetup(account_name=name, account_number=number, qr_image_file_id=qr_file_id)
        return await self._service.upsert(admin_id, "primary", CurrencyCode(currency), setup)


def build_admin_payment_accounts_router(
    handler: TelegramAdminPaymentAccountHandler,
    identity_handler: Any,
) -> Router:
    router = Router(name="admin-payment-accounts")

    async def _authorize(user_id: int) -> Any:
        return await identity_handler.list_pending(user_id)

    def cancel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ إلغاء والتراجع", callback_data="admin:payment:list")]
        ])

    @router.callback_query(F.data == "admin:payment:list")
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def list_accounts_callback(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        await state.clear()
        try:
            accounts = await handler.list_accounts(user_id)
        except Exception:
            await query.answer("تعذر جلب الحسابات.", show_alert=True)
            return

        await query.answer()
        lines = ["💳 **إدارة حسابات الدفع (ShamCash)**", ""]
        rows = []
        
        for acc in accounts:
            status = "✅ مفعل" if acc.is_active else "❌ معطل"
            lines.append(f"• عملة: {acc.currency.value}")
            lines.append(f"  الاسم: {acc.account_name}")
            lines.append(f"  الرقم: {acc.account_number}")
            lines.append(f"  الحالة: {status}\n")
            
            toggle_text = "تعطيل" if acc.is_active else "تفعيل"
            toggle_action = "disable" if acc.is_active else "enable"
            
            rows.append([
                InlineKeyboardButton(text=f"✏️ تعديل {acc.currency.value}", callback_data=f"admin:payment:edit:{acc.currency.value}"),
                InlineKeyboardButton(text=f"🔄 {toggle_text} {acc.currency.value}", callback_data=f"admin:payment:toggle:{acc.currency.value}:{toggle_action}")
            ])
            
        # Add options for currencies not in DB yet (NEW.SYP, USD)
        existing_currencies = {acc.currency.value for acc in accounts}
        for cur in ["NEW.SYP", "USD"]:
            if cur not in existing_currencies:
                rows.append([InlineKeyboardButton(text=f"➕ إضافة حساب {cur}", callback_data=f"admin:payment:edit:{cur}")])

        rows.append([InlineKeyboardButton(text="🔙 العودة للوحة التحكم", callback_data="admin:dashboard")])
        
        await query.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.startswith("admin:payment:toggle:"))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def toggle_account_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        parts = str(query.data).split(":")
        currency = parts[3]
        action = parts[4]
        is_active = action == "enable"

        try:
            await handler.toggle_active(user_id, currency, is_active)
            await list_accounts_callback(query, FSMContext(storage=None, key=None)) # We just call it manually
        except Exception:
            await query.answer("فشلت العملية.", show_alert=True)

    @router.callback_query(F.data.startswith("admin:payment:edit:"))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def edit_account_callback(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return

        currency = str(query.data).split(":")[-1]
        await state.update_data(payment_currency=currency)
        await state.set_state(AdminPaymentAccountStates.waiting_for_account_name)
        await query.answer()
        await query.message.edit_text(f"✏️ جاري إعداد حساب لعملة {currency}\n\nالرجاء إدخال اسم الحساب المستلم:", reply_markup=cancel_markup())

    @router.message(AdminPaymentAccountStates.waiting_for_account_name)
    async def process_account_name(message: Message, state: FSMContext) -> None:
        name = message.text.strip()
        if not name:
            await message.answer("اسم غير صالح.", reply_markup=cancel_markup())
            return
        await state.update_data(payment_name=name)
        await state.set_state(AdminPaymentAccountStates.waiting_for_account_number)
        await message.answer("الرجاء إدخال رقم الحساب المستلم (أو المعرف):", reply_markup=cancel_markup())

    @router.message(AdminPaymentAccountStates.waiting_for_account_number)
    async def process_account_number(message: Message, state: FSMContext) -> None:
        number = message.text.strip()
        if not number:
            await message.answer("رقم غير صالح.", reply_markup=cancel_markup())
            return
        await state.update_data(payment_number=number)
        await state.set_state(AdminPaymentAccountStates.waiting_for_qr_image)
        await message.answer("الرجاء إرسال صورة الـ QR Code الخاصة بالحساب:", reply_markup=cancel_markup())

    @router.message(AdminPaymentAccountStates.waiting_for_qr_image, F.photo)
    async def process_qr_image(message: Message, state: FSMContext) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
            
        data = await state.get_data()
        currency = data.get("payment_currency")
        name = data.get("payment_name")
        number = data.get("payment_number")
        
        file_id = message.photo[-1].file_id
        
        try:
            await handler.upsert(user_id, currency, name, number, file_id)
            await message.answer(f"✅ تم حفظ وتحديث بيانات حساب {currency} بنجاح.")
            await state.clear()
        except Exception as e:
            await message.answer(f"❌ حدث خطأ: {str(e)}", reply_markup=cancel_markup())

    return router
