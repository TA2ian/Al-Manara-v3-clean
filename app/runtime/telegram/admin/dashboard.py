"""Admin dashboard Telegram handler — /admin command and navigation."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.admin.fulfillment import (
    TelegramFulfillmentHandler,
    fulfillment_action_markup,
)
from app.runtime.telegram.admin.order_listing import (
    ADMIN_ORDER_PAGE_SIZE,
    TelegramAdminOrderListingHandler,
    TelegramAdminOrderListingInput,
)
from app.runtime.telegram.admin.order_review import order_action_markup
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message

ADMIN_DASHBOARD_CALLBACK = "admin:dashboard"
ADMIN_IDENTITY_CALLBACK = "admin:identity_pending"
ADMIN_ORDERS_CALLBACK = "admin:orders"
ADMIN_REVIEW_ORDERS_CALLBACK = "admin:review_orders"
ADMIN_FULFILLMENT_CALLBACK = "admin:fulfillment"


def admin_dashboard_markup(*, include_orders: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👥 التحقق من المستخدمين", callback_data=ADMIN_IDENTITY_CALLBACK)]]
    if include_orders:
        rows.append([InlineKeyboardButton(text="📦 الطلبات النشطة", callback_data=ADMIN_ORDERS_CALLBACK)])
        rows.append([InlineKeyboardButton(text="🔎 المدفوعات قيد المراجعة", callback_data=ADMIN_REVIEW_ORDERS_CALLBACK)])
        rows.append([InlineKeyboardButton(text="🚚 الطلبات المعتمدة للتنفيذ", callback_data=ADMIN_FULFILLMENT_CALLBACK)])
        rows.append([
            InlineKeyboardButton(text="💳 حسابات الدفع", callback_data="admin:payment:list"),
            InlineKeyboardButton(text="⚙️ إعدادات الإيصالات", callback_data="admin:settings:receipt")
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render_orders(
    page: Any,
    *,
    review_actions: bool = False,
    fulfillment_actions: bool = False,
    current_admin_user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page.items:
        if review_actions:
            empty = msg.ADMIN_ORDERS_EMPTY_REVIEW
        elif fulfillment_actions:
            empty = msg.ADMIN_ORDERS_EMPTY_FULFILLMENT
        else:
            empty = msg.ADMIN_ORDERS_EMPTY_ACTIVE
        return empty, None

    if review_actions:
        title = "🔎 طلبات قيد المراجعة"
    elif fulfillment_actions:
        title = "🚚 الطلبات المعتمدة للتنفيذ"
    else:
        title = "📦 الطلبات النشطة"

    lines = [f"{title} ({page.total_count})", ""]
    rows: list[list[InlineKeyboardButton]] = []

    for item in page.items:
        lines.append(
            f"• {item.public_order_code} | {item.status}\n"
            f"  العميل: {item.user_telegram_id}\n"
            f"  الشبكة: {item.network_code}"
        )
        if review_actions:
            rows.append([InlineKeyboardButton(
                text="🔎 مراجعة التفاصيل والإيصال",
                callback_data=f"admin:order:details:{item.internal_order_id}"
            )])
        elif fulfillment_actions:
            if item.fulfillment_claimed_by is None:
                rows.extend(fulfillment_action_markup(item.internal_order_id, item.version, claimed=False).inline_keyboard)
            elif item.fulfillment_claimed_by == current_admin_user_id:
                rows.extend(fulfillment_action_markup(item.internal_order_id, item.version, claimed=True).inline_keyboard)
            else:
                lines.append(f"  {msg.ADMIN_ORDER_CLAIMED_BY_OTHER}")

        # Super admin quick action row for each order
        super_admin_row = [
            InlineKeyboardButton(text="🔄 إعادة فتح", callback_data=f"admin:order:reset:{item.internal_order_id}"),
            InlineKeyboardButton(text="✏️ تعديل", callback_data=f"admin:order:edit:{item.internal_order_id}"),
            InlineKeyboardButton(text="⚡ تخطي OCR", callback_data=f"admin:order:bypass:{item.internal_order_id}"),
            InlineKeyboardButton(text="🗑️ حذف", callback_data=f"admin:order:delete:{item.internal_order_id}"),
        ]
        rows.append(super_admin_row)

    if page.total_count > page.page_size:
        lines.append(f"\nالصفحة {page.page + 1}")

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def build_admin_dashboard_router(
    identity_handler: Any,
    order_listing: TelegramAdminOrderListingHandler | None = None,
) -> Router:
    router = Router(name="admin-dashboard")

    async def _authorize(user_id: int) -> Any:
        return await identity_handler.list_pending(user_id)

    @router.message(Command("admin"))
    @require_private_message(msg.ADMIN_PRIVATE_ONLY)
    async def admin_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await message.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED))
            return
        await message.answer(
            msg.ADMIN_DASHBOARD_TITLE,
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.callback_query(F.data == ADMIN_DASHBOARD_CALLBACK)
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def dashboard_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            msg.ADMIN_DASHBOARD_TITLE,
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.callback_query(F.data == ADMIN_IDENTITY_CALLBACK)
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def identity_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        auth = await _authorize(user_id)
        if not auth.ok:
            await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
            return
        await query.answer()
        if not auth.submissions:
            await query.message.answer(msg.ADMIN_NO_PENDING_IDENTITY)
            return
        lines = ["👥 طلبات التحقق المعلقة", ""]
        for sub in auth.submissions:
            lines.append(f"• المستخدم: {getattr(sub, 'telegram_user_id', '?')}")
        await query.message.answer("\n".join(lines))

    if order_listing is not None:
        async def _load_order_list(query: CallbackQuery, list_type: str) -> None:
            user_id = await get_user_id_from_callback(query)
            if user_id is None:
                return
            auth = await _authorize(user_id)
            if not auth.ok:
                await query.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED), show_alert=True)
                return
            await query.answer()
            response = await order_listing.handle(
                TelegramAdminOrderListingInput(
                    admin_user_id=user_id,
                    actor_type="primary",
                    list_type=list_type,
                    page=0,
                    page_size=ADMIN_ORDER_PAGE_SIZE,
                )
            )
            if not response.ok or response.page is None:
                await query.message.answer(msg.safe(response.message, msg.ADMIN_ORDERS_LOAD_FAILED))
                return
            text, markup = _render_orders(
                response.page,
                review_actions=(list_type == "review"),
                fulfillment_actions=(list_type == "fulfillment"),
                current_admin_user_id=user_id,
            )
            await query.message.answer(text, reply_markup=markup)

        @router.callback_query(F.data == ADMIN_ORDERS_CALLBACK)
        @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
        async def orders_callback(query: CallbackQuery) -> None:
            await _load_order_list(query, "active")

        @router.callback_query(F.data == ADMIN_REVIEW_ORDERS_CALLBACK)
        @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
        async def review_orders_callback(query: CallbackQuery) -> None:
            await _load_order_list(query, "review")

        @router.callback_query(F.data == ADMIN_FULFILLMENT_CALLBACK)
        @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
        async def fulfillment_callback(query: CallbackQuery) -> None:
            await _load_order_list(query, "fulfillment")

    return router
