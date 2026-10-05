"""Customer purchase order Telegram handler — full buy flow via FSM."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.create_purchase_order import CreatePurchaseOrderCommand, CreatePurchaseOrderService
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import (
    get_user_id_from_callback,
    get_user_id_from_message,
    require_private_callback,
    require_private_message,
)

BUY_START_CALLBACK = "customer:buy"
BUY_CURRENCY_CALLBACK = "customer:buy:currency"
BUY_NETWORK_CALLBACK = "customer:buy:network"
BUY_WALLET_CALLBACK = "customer:buy:wallet"

SUPPORTED_CURRENCIES = [("NEW_SYP", "ليرة سورية جديدة"), ("USD", "دولار أمريكي")]
SUPPORTED_NETWORKS = [("BEP20", "BEP20 (BSC)"), ("TRC20", "TRC20 (TRON)")]


class PurchaseOrderStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency = State()
    waiting_for_network = State()
    waiting_for_wallet = State()
    waiting_for_wallet_address = State()
    waiting_for_confirmation = State()


def cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:buy:cancel")]
    ])


def currency_selection_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{BUY_CURRENCY_CALLBACK}:{code}")]
        for code, label in SUPPORTED_CURRENCIES
    ] + [[InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:buy:cancel")]])


def network_selection_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{BUY_NETWORK_CALLBACK}:{code}")]
        for code, label in SUPPORTED_NETWORKS
    ] + [[InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:buy:cancel")]])


def wallet_selection_markup(wallets: list[Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"💳 {w.network_code}: {w.address[:8]}...{w.address[-6:]}",
            callback_data=f"{BUY_WALLET_CALLBACK}:{w.wallet_id}",
        )]
        for w in wallets
    ]
    rows.append([InlineKeyboardButton(text="✏️ إدخال عنوان محفظة يدوي", callback_data="customer:buy:wallet:manual")])
    rows.append([InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:buy:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_quote(quote: Any) -> str:
    f = quote.financials
    lines = [
        "📋 ملخص الطلب",
        "",
        f"المبلغ المطلوب: {f.requested_amount} USDT",
        f"رسوم الخدمة: {f.fee_amount} USDT ({f.fee_percent}%)",
        f"رسم الشبكة الثابت: {f.network_fixed_fee_usdt} USDT",
        f"إجمالي الرسوم: {f.total_fee_usdt} USDT",
        f"صافي USDT: {f.net_usdt_amount} USDT",
        f"مبلغ الدفع: {f.local_amount} {f.payment_currency}",
        "",
        "هل تريد تأكيد الطلب؟",
    ]
    return "\n".join(lines)


def confirm_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأكيد", callback_data="customer:buy:confirm"),
            InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:buy:cancel"),
        ]
    ])


from typing import Callable, Awaitable
def build_customer_purchase_order_router(
    order_service: CreatePurchaseOrderService,
    wallet_listing_service: Any,
    notify_admins: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Router:
    router = Router(name="customer-purchase-order")

    async def _start_buy(message: Message, user_id: int, state: FSMContext) -> None:
        await state.clear()
        await state.update_data(user_id=user_id)
        await state.set_state(PurchaseOrderStates.waiting_for_amount)
        await message.answer(
            "💰 أدخل مبلغ الـ USDT المطلوب شراؤه:\n"
            "<i>(ملاحظة: للعملاء غير الموثقين، الحد المسموح هو بين 10 و 50 USDT)</i>",
            parse_mode="HTML",
            reply_markup=cancel_markup()
        )

    @router.message(Command("buy"))
    @require_private_message(msg.DASHBOARD_PRIVATE_ONLY)
    async def buy_command(message: Message, state: FSMContext) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        await _start_buy(message, user_id, state)

    @router.callback_query(F.data == BUY_START_CALLBACK)
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def buy_callback(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        await query.answer()
        await _start_buy(query.message, user_id, state)

    @router.message(PurchaseOrderStates.waiting_for_amount)
    async def receive_amount(message: Message, state: FSMContext) -> None:
        if not message.text:
            await message.answer(msg.ORDER_INVALID_INPUT, reply_markup=cancel_markup())
            return
        try:
            amount = Decimal(message.text.strip())
        except InvalidOperation:
            await message.answer(msg.ORDER_INVALID_INPUT, reply_markup=cancel_markup())
            return
        if not amount.is_finite() or amount <= 0:
            await message.answer(msg.ORDER_INVALID_INPUT, reply_markup=cancel_markup())
            return
        await state.update_data(requested_amount=str(amount))
        await state.set_state(PurchaseOrderStates.waiting_for_currency)
        await message.answer(msg.ORDER_PROMPT_CURRENCY, reply_markup=currency_selection_markup())

    @router.callback_query(F.data.startswith(BUY_CURRENCY_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def currency_selected(query: CallbackQuery, state: FSMContext) -> None:
        currency = str(query.data).split(":")[-1]
        await state.update_data(payment_currency=currency)
        await state.set_state(PurchaseOrderStates.waiting_for_network)
        await query.answer()
        await query.message.answer(msg.ORDER_PROMPT_NETWORK, reply_markup=network_selection_markup())

    @router.callback_query(F.data.startswith(BUY_NETWORK_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def network_selected(query: CallbackQuery, state: FSMContext) -> None:
        network = str(query.data).split(":")[-1]
        await state.update_data(network_code=network)
        data = await state.get_data()
        user_id = data.get("user_id")
        if user_id is None:
            await query.answer(msg.IDENTITY_CHECK_FAILED, show_alert=True)
            await state.clear()
            return
        # Load wallets for this user
        try:
            all_wallets = await wallet_listing_service.list_wallets(user_id) or []
            wallets = [w for w in all_wallets if getattr(w, "network_code", "") == network or getattr(w, "network", None) == network]
        except Exception:
            wallets = []

        if not wallets:
            # If no wallets found, prompt to enter address directly
            await state.set_state(PurchaseOrderStates.waiting_for_wallet_address)
            await query.answer()
            await query.message.answer(
                f"📝 يرجى إرسال عنوان محفظتك لاستلام الـ USDT على شبكة <b>{network}</b>:",
                parse_mode="HTML",
                reply_markup=cancel_markup()
            )
            return

        await state.update_data(wallets=[{"wallet_id": str(w.wallet_id), "address": w.address, "network_code": network} for w in wallets])
        await state.set_state(PurchaseOrderStates.waiting_for_wallet)
        await query.answer()
        await query.message.answer(msg.ORDER_PROMPT_WALLET, reply_markup=wallet_selection_markup(wallets))

    @router.callback_query(F.data == "customer:buy:wallet:manual")
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def manual_wallet_callback(query: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        network = data.get("network_code", "BEP20")
        await state.set_state(PurchaseOrderStates.waiting_for_wallet_address)
        await query.answer()
        await query.message.answer(
            f"📝 يرجى إرسال عنوان محفظتك لاستلام الـ USDT على شبكة <b>{network}</b>:",
            parse_mode="HTML",
            reply_markup=cancel_markup()
        )

    @router.message(PurchaseOrderStates.waiting_for_wallet_address)
    async def receive_wallet_address(message: Message, state: FSMContext) -> None:
        if not message.text:
            await message.answer("يرجى إرسال عنوان المحفظة كنص.", reply_markup=cancel_markup())
            return
        address = message.text.strip()
        data = await state.get_data()
        network = data.get("network_code", "BEP20")
        user_id = data.get("user_id")
        if user_id is None:
            await message.answer("حدث خطأ في الجلسة. يرجى البدء من جديد عبر /start")
            await state.clear()
            return

        import re
        if network == "BEP20":
            if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
                await message.answer("❌ عنوان المحفظة غير صالح لشبكة BEP20 (يجب أن يبدأ بـ 0x ويتكون من 42 خانة).\nيرجى إعادة إرسال العنوان الصحيح:", reply_markup=cancel_markup())
                return
        elif network == "TRC20":
            if not re.match(r"^T[1-9A-HJ-NP-Za-km-z]{33}$", address):
                await message.answer("❌ عنوان المحفظة غير صالح لشبكة TRC20 (يجب أن يبدأ بحرف T ويتكون من 34 خانة).\nيرجى إعادة إرسال العنوان الصحيح:", reply_markup=cancel_markup())
                return

        try:
            wallet = await order_service._wallets.get_or_create_wallet_for_user(user_id=user_id, address=address, network=network)
            wallet_id_str = str(wallet.wallet_id)
        except Exception:
            await message.answer("تعذر حفظ عنوان المحفظة. يرجى المحاولة لاحقاً.", reply_markup=cancel_markup())
            return

        await state.update_data(wallet_id=wallet_id_str)
        await _show_quote_preview(message, state, user_id, wallet_id_str, data)

    async def _show_quote_preview(target: Message | CallbackQuery, state: FSMContext, user_id: int, wallet_id_str: str, data: dict) -> None:
        try:
            command = CreatePurchaseOrderCommand(
                user_id=user_id,
                wallet_id=UUID(wallet_id_str),
                network_code=data["network_code"],
                requested_amount=Decimal(data["requested_amount"]),
                payment_currency=data["payment_currency"],
                idempotency_key=str(uuid4()),
            )
            quote = await order_service.preview(command)
            await state.update_data(
                quote_key=str(uuid4()),
                saved_quote=quote.to_dict()
            )
            await state.set_state(PurchaseOrderStates.waiting_for_confirmation)
            text = render_quote(quote)
            markup = confirm_markup()
            if isinstance(target, CallbackQuery):
                await target.answer()
                await target.message.answer(text, reply_markup=markup)
            else:
                await target.answer(text, reply_markup=markup)
        except ValueError as exc:
            err = str(exc)
            msg_text = err if ("العملاء غير الموثقين" in err or "بين 10 و 50" in err) else (
                msg.ORDER_NOT_VERIFIED if "verified" in err else (
                    msg.ORDER_NETWORK_UNAVAILABLE if "network" in err else msg.ORDER_INVALID_INPUT
                )
            )
            if isinstance(target, CallbackQuery):
                await target.answer()
                await target.message.answer(msg_text)
            else:
                await target.answer(msg_text)
            await state.clear()
        except RuntimeError as exc:
            err_text = str(exc)
            if isinstance(target, CallbackQuery):
                await target.answer()
                await target.message.answer(err_text)
            else:
                await target.answer(err_text)
            await state.clear()
        except Exception:
            if isinstance(target, CallbackQuery):
                await target.answer()
                await target.message.answer(msg.GENERIC_ERROR)
            else:
                await target.answer(msg.GENERIC_ERROR)
            await state.clear()

    @router.callback_query(F.data.startswith(BUY_WALLET_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def wallet_selected(query: CallbackQuery, state: FSMContext) -> None:
        wallet_id_str = str(query.data).split(":")[-1]
        await state.update_data(wallet_id=wallet_id_str)
        data = await state.get_data()
        user_id = data.get("user_id")
        if user_id is None:
            await query.answer(msg.IDENTITY_CHECK_FAILED, show_alert=True)
            await state.clear()
            return
        await _show_quote_preview(query, state, user_id, wallet_id_str, data)

    @router.callback_query(F.data == "customer:buy:confirm")
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def confirm_order(query: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("user_id")
        if user_id is None:
            await query.answer(msg.IDENTITY_CHECK_FAILED, show_alert=True)
            await state.clear()
            return
        try:
            command = CreatePurchaseOrderCommand(
                user_id=user_id,
                wallet_id=UUID(data["wallet_id"]),
                network_code=data["network_code"],
                requested_amount=Decimal(data["requested_amount"]),
                payment_currency=data["payment_currency"],
                idempotency_key=data.get("quote_key") or str(uuid4()),
            )
            
            from app.application.quote import PurchaseQuote
            saved_quote_dict = data.get("saved_quote")
            provided_quote = PurchaseQuote.from_dict(saved_quote_dict) if saved_quote_dict else None
            
            result = await order_service.create(command, provided_quote=provided_quote)
            await state.clear()
            await query.answer()
            await query.message.answer(
                msg.ORDER_CREATED.format(order_code=getattr(result, "public_order_code", "—"))
            )
            # Notify Admins
            if notify_admins and getattr(result, "public_order_code", None):
                code = result.public_order_code
                amt = command.requested_amount
                net = command.network_code
                await notify_admins(f"🆕 طلب شراء جديد:\nرمز الطلب: [{code}]\nالمبلغ: {amt} USDT\nالشبكة: {net}", query.bot)
        except LookupError:
            await query.answer()
            await state.clear()
            await query.message.answer(msg.WALLET_NOT_AVAILABLE)
        except ValueError as exc:
            await query.answer()
            await state.clear()
            err = str(exc)
            if "بين 10 و 50" in err or "العملاء غير الموثقين" in err:
                await query.message.answer(err)
            elif "verified" in err:
                await query.message.answer(msg.ORDER_NOT_VERIFIED)
            elif "network" in err:
                await query.message.answer(msg.ORDER_NETWORK_UNAVAILABLE)
            elif "expired" in err.lower():
                await query.message.answer("انتهت صلاحية العرض الزمني. الرجاء بدء عملية شراء جديدة للحصول على تسعيرة محدثة.")
            else:
                await query.message.answer(msg.ORDER_INVALID_INPUT)
        except Exception as exc:
            await query.answer()
            await state.clear()
            err = str(exc)
            if "max 1 order per day" in err or "1 order per day" in err:
                await query.message.answer("⚠️ الحد المسموح للعميل غير الموثق هو طلب واحد فقط في اليوم.\nيمكنك توثيق هويتك لرفع القيود.")
            elif "max 3 orders per week" in err or "3 orders per week" in err:
                await query.message.answer("⚠️ الحد المسموح للعميل غير الموثق هو 3 طلبات في الأسبوع.\nيمكنك توثيق هويتك لرفع القيود.")
            elif "max 10 orders per month" in err or "10 orders per month" in err:
                await query.message.answer("⚠️ الحد المسموح للعميل غير الموثق هو 10 طلبات في الشهر.\nيمكنك توثيق هويتك لرفع القيود.")
            elif "between 10 and 50" in err:
                await query.message.answer("⚠️ للعملاء غير الموثقين، الحد المسموح للطلب هو بين 10 و 50 دولار فقط.\nيمكنك توثيق هويتك لرفع سقف الطلبات.")
            else:
                await query.message.answer(msg.ORDER_CONFLICT)

    @router.callback_query(F.data == "customer:buy:cancel")
    async def cancel_order(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await query.answer()
        await query.message.answer("تم إلغاء الطلب.")

    return router
