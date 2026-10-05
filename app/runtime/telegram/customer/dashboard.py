"""Customer dashboard Telegram handler — /start and inline navigation."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import (
    get_user_id_from_callback,
    require_private_callback,
    require_private_message,
)

DASHBOARD_CALLBACK = "customer:dashboard"
DASHBOARD_ORDERS_CALLBACK = "customer:orders"
DASHBOARD_WALLETS_CALLBACK = "customer:wallets"
DASHBOARD_VERIFY_CALLBACK = "customer:verify"
DASHBOARD_BUY_CALLBACK = "customer:buy"


def customer_dashboard_markup(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🪪 التحقق من الهوية", callback_data=DASHBOARD_VERIFY_CALLBACK),
            InlineKeyboardButton(text="👛 محافظي", callback_data=DASHBOARD_WALLETS_CALLBACK),
        ],
        [InlineKeyboardButton(text="🛒 إنشاء طلب شراء", callback_data=DASHBOARD_BUY_CALLBACK)],
        [InlineKeyboardButton(text="📦 طلباتي", callback_data=DASHBOARD_ORDERS_CALLBACK)],
    ]
    if is_admin:
        from app.runtime.telegram.admin.dashboard import ADMIN_DASHBOARD_CALLBACK
        rows.append([InlineKeyboardButton(text="🛡️ لوحة تحكم الأدمن", callback_data=ADMIN_DASHBOARD_CALLBACK)])
        
    return InlineKeyboardMarkup(inline_keyboard=rows)


from typing import Awaitable, Callable

def build_customer_dashboard_router(is_admin_fn: Callable[[int], Awaitable[bool]] | None = None) -> Router:
    """Dashboard router — does not depend on any composition; buttons route to other routers."""
    router = Router(name="customer-dashboard")

    async def _resolve_admin(user_id: int | None) -> bool:
        if not user_id or not is_admin_fn:
            return False
        return await is_admin_fn(user_id)

    @router.message(CommandStart())
    @router.message(F.text.startswith("/start "))
    @require_private_message(msg.DASHBOARD_PRIVATE_ONLY)
    async def start(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else None
        is_admin = await _resolve_admin(user_id)
        await message.answer(msg.DASHBOARD_WELCOME, reply_markup=customer_dashboard_markup(is_admin=is_admin))

    @router.callback_query(F.data == DASHBOARD_CALLBACK)
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def dashboard_callback(query: CallbackQuery) -> None:
        user_id = query.from_user.id
        is_admin = await _resolve_admin(user_id)
        await query.answer()
        await query.message.edit_text(
            msg.DASHBOARD_WELCOME, reply_markup=customer_dashboard_markup(is_admin=is_admin)
        )

    return router
