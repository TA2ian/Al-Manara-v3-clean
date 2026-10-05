"""Customer wallet management Telegram handlers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message

WALLET_LIST_CALLBACK = "customer:wallets"
WALLET_DISABLE_CALLBACK = "customer:wallet:disable"
WALLET_ADD_CALLBACK = "customer:wallet:add"
WALLET_NETWORK_CALLBACK = "customer:wallet:network"

SUPPORTED_NETWORKS = [("BEP20", "BEP20 (BSC)"), ("TRC20", "TRC20 (TRON)")]


class WalletStates(StatesGroup):
    waiting_for_address = State()
    waiting_for_network_confirmation = State()


@dataclass(frozen=True, slots=True)
class TelegramWalletListInput:
    authenticated_telegram_user_id: int


@dataclass(frozen=True, slots=True)
class TelegramWalletListResponse:
    ok: bool
    text: str
    wallets: list[Any] | None = None


@dataclass(frozen=True, slots=True)
class TelegramWalletRegisterInput:
    authenticated_telegram_user_id: int
    address: str
    network_code: str


@dataclass(frozen=True, slots=True)
class TelegramWalletDisableInput:
    authenticated_telegram_user_id: int
    wallet_id: UUID


class TelegramWalletHandler:
    def __init__(self, listing: Any, registration: Any, disabling: Any) -> None:
        self._listing = listing
        self._registration = registration
        self._disabling = disabling

    async def list(self, user_id: int) -> TelegramWalletListResponse:
        try:
            result = await self._listing.list_wallets(user_id)
            if not result:
                return TelegramWalletListResponse(True, msg.WALLETS_EMPTY, [])
            lines = ["👛 محافظك المسجلة", ""]
            wallets = []
            for w in result:
                lines.append(f"• {w.network_code}: {w.address[:8]}...{w.address[-6:]}")
                wallets.append(w)
            return TelegramWalletListResponse(True, "\n".join(lines), wallets)
        except Exception:
            return TelegramWalletListResponse(False, msg.WALLETS_LOAD_FAILED)

    async def register(self, data: TelegramWalletRegisterInput) -> bool:
        try:
            await self._registration.register(
                telegram_user_id=data.authenticated_telegram_user_id,
                address=data.address,
                network_code=data.network_code,
            )
            return True
        except Exception:
            return False

    async def disable(self, data: TelegramWalletDisableInput) -> bool:
        try:
            await self._disabling.disable(
                telegram_user_id=data.authenticated_telegram_user_id,
                wallet_id=data.wallet_id,
            )
            return True
        except Exception:
            return False


def wallet_listing_markup(wallets: list[Any] | None) -> InlineKeyboardMarkup | None:
    if not wallets:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ إضافة محفظة", callback_data=WALLET_ADD_CALLBACK)]
        ])
    rows: list[list[InlineKeyboardButton]] = []
    for w in wallets:
        short = f"{w.address[:6]}...{w.address[-4:]}" if len(w.address) > 12 else w.address
        rows.append([
            InlineKeyboardButton(
                text=f"❌ تعطيل {w.network_code} ({short})",
                callback_data=f"{WALLET_DISABLE_CALLBACK}:{w.wallet_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="➕ إضافة محفظة", callback_data=WALLET_ADD_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def network_selection_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{WALLET_NETWORK_CALLBACK}:{code}")]
        for code, label in SUPPORTED_NETWORKS
    ])


def build_customer_wallets_router(handler: TelegramWalletHandler) -> Router:
    router = Router(name="customer-wallets")

    @router.message(Command("wallets"))
    @require_private_message(msg.DASHBOARD_PRIVATE_ONLY)
    async def wallets_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        response = await handler.list(user_id)
        markup = wallet_listing_markup(response.wallets) if response.ok else None
        await message.answer(response.text, reply_markup=markup)

    @router.callback_query(F.data == WALLET_LIST_CALLBACK)
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def wallets_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        response = await handler.list(user_id)
        await query.answer()
        markup = wallet_listing_markup(response.wallets) if response.ok else None
        await query.message.answer(response.text, reply_markup=markup)

    def cancel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:wallet:cancel")]
        ])

    @router.callback_query(F.data == "customer:wallet:cancel")
    async def cancel_wallet(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await query.answer()
        await query.message.answer("تم الإلغاء.")

    @router.callback_query(F.data == WALLET_ADD_CALLBACK)
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def add_wallet_callback(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        await query.answer()
        await state.set_state(WalletStates.waiting_for_address)
        await state.update_data(user_id=user_id)
        await query.message.answer(msg.WALLET_REGISTER_PROMPT, reply_markup=cancel_markup())

    @router.message(WalletStates.waiting_for_address)
    async def receive_wallet_address(message: Message, state: FSMContext) -> None:
        if not message.text:
            await message.answer(msg.WALLET_REGISTER_FAILED, reply_markup=cancel_markup())
            return
        await state.update_data(address=message.text.strip())
        await state.set_state(WalletStates.waiting_for_network_confirmation)
        
        markup = network_selection_markup()
        markup.inline_keyboard.append([InlineKeyboardButton(text="❌ إلغاء", callback_data="customer:wallet:cancel")])
        await message.answer("اختر الشبكة:", reply_markup=markup)

    @router.callback_query(F.data.startswith(WALLET_NETWORK_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def network_selected(query: CallbackQuery, state: FSMContext) -> None:
        network_code = str(query.data).split(":")[-1]
        data = await state.get_data()
        address = data.get("address", "")
        user_id = data.get("user_id") or await get_user_id_from_callback(query)
        if not address or user_id is None:
            await query.answer(msg.GENERIC_ERROR, show_alert=True)
            await state.clear()
            return
        success = await handler.register(TelegramWalletRegisterInput(
            authenticated_telegram_user_id=user_id,
            address=address,
            network_code=network_code,
        ))
        await state.clear()
        await query.answer()
        await query.message.answer(msg.WALLET_REGISTER_SUCCESS if success else msg.WALLET_REGISTER_FAILED)

    @router.callback_query(F.data.startswith(WALLET_DISABLE_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def disable_wallet_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        try:
            wallet_id = UUID(str(query.data).split(":")[-1])
        except ValueError:
            await query.answer("معرّف المحفظة غير صالح.", show_alert=True)
            return
        success = await handler.disable(TelegramWalletDisableInput(
            authenticated_telegram_user_id=user_id,
            wallet_id=wallet_id,
        ))
        await query.answer()
        await query.message.answer(msg.WALLET_DISABLE_SUCCESS if success else msg.WALLET_DISABLE_FAILED)

    return router
