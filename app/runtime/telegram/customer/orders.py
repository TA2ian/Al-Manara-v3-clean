"""Customer order listing and details Telegram handler."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.customer_order_listing import ListCustomerOrdersCommand
from app.application.customer_order_details import GetCustomerOrderDetailsCommand
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message

ORDER_PAGE_SIZE = 5
ORDERS_PAGE_CALLBACK = "customer:orders:page"
ORDER_OPEN_CALLBACK = "customer:orders:open"
ORDER_RECEIPT_CALLBACK = "customer:orders:receipt"


@dataclass(frozen=True, slots=True)
class TelegramCustomerOrderListingInput:
    authenticated_telegram_user_id: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class TelegramCustomerOrderListingResponse:
    ok: bool
    message: str
    page: Any | None = None


class TelegramCustomerOrderListingHandler:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def handle(self, data: TelegramCustomerOrderListingInput) -> TelegramCustomerOrderListingResponse:
        if data.authenticated_telegram_user_id <= 0:
            return TelegramCustomerOrderListingResponse(False, msg.IDENTITY_CHECK_FAILED)
        try:
            result = await self._service.list(ListCustomerOrdersCommand(
                customer_telegram_user_id=data.authenticated_telegram_user_id,
                page=data.page,
                page_size=data.page_size,
            ))
            return TelegramCustomerOrderListingResponse(True, "", result)
        except Exception:
            return TelegramCustomerOrderListingResponse(False, msg.ORDERS_LOAD_FAILED)


class TelegramCustomerOrderDetailsHandler:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def handle(self, user_id: int, public_code: str):
        if user_id <= 0:
            return False, msg.IDENTITY_CHECK_FAILED, None
        try:
            result = await self._service.get(GetCustomerOrderDetailsCommand(
                customer_telegram_user_id=user_id,
                public_order_code=public_code,
            ))
            if result is None:
                return False, "الطلب غير موجود أو لا تملك صلاحية الوصول إليه.", None
            return True, "", result
        except Exception:
            return False, "تعذر تحميل تفاصيل الطلب.", None


def render_order_listing_failure(error_msg: str | None = None) -> str:
    return msg.safe(error_msg, msg.ORDERS_LOAD_FAILED)


def render_order_page(page: Any) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page or not page.items:
        return msg.ORDERS_EMPTY, None
    lines = ["📦 طلباتك الأخيرة\n"]
    rows: list[list[InlineKeyboardButton]] = []
    
    for item in page.items:
        # Create a button for each order
        text_status = "⏳" if item.status.value in ("PENDING_PAYMENT", "UNDER_REVIEW") else "✅" if item.status.value == "COMPLETED" else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{text_status} {item.public_order_code} | {item.requested_amount} USDT",
                callback_data=f"{ORDER_OPEN_CALLBACK}:{item.public_order_code}"
            )
        ])

    nav_row = []
    if hasattr(page, 'total_count') and page.total_count > page.page_size:
        if page.page > 0:
            nav_row.append(InlineKeyboardButton(text="◀ السابق", callback_data=f"{ORDERS_PAGE_CALLBACK}:{page.page - 1}"))
        if (page.page + 1) * page.page_size < page.total_count:
            nav_row.append(InlineKeyboardButton(text="التالي ▶", callback_data=f"{ORDERS_PAGE_CALLBACK}:{page.page + 1}"))
    if nav_row:
        rows.append(nav_row)
        
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def render_order_details(order: Any) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        f"📋 تفاصيل الطلب: {order.public_order_code}",
        "─" * 20,
        f"الحالة: {order.status.value}",
        f"تاريخ الإنشاء: {order.created_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"المبلغ المطلوب: {order.requested_amount} USDT",
        f"شبكة التحويل: {order.network_code}",
        f"المبلغ الواجب دفعه: {order.local_amount} {order.payment_currency}" if order.local_amount else "",
    ]
    
    rows = []
    if order.status.value == "PENDING_PAYMENT":
        rows.append([
            InlineKeyboardButton(
                text="💳 إرسال الإيصال",
                callback_data=f"{ORDER_RECEIPT_CALLBACK}:{order.public_order_code}"
            )
        ])
        
    rows.append([InlineKeyboardButton(text="🔙 عودة للطلبات", callback_data="customer:orders")])
    
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def build_customer_orders_router(
    listing_handler: TelegramCustomerOrderListingHandler,
    details_handler: TelegramCustomerOrderDetailsHandler,
) -> Router:
    router = Router(name="customer-orders")

    @router.message(Command("orders"))
    @require_private_message(msg.DASHBOARD_PRIVATE_ONLY)
    async def orders_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
        response = await listing_handler.handle(TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=user_id,
            page=0,
            page_size=ORDER_PAGE_SIZE,
        ))
        if not response.ok or response.page is None:
            await message.answer(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await message.answer(text, reply_markup=markup)

    @router.callback_query(F.data == "customer:orders")
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def orders_first_page_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        await query.answer()
        response = await listing_handler.handle(TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=user_id,
            page=0,
            page_size=ORDER_PAGE_SIZE,
        ))
        if not response.ok or response.page is None:
            await query.message.edit_text(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await query.message.edit_text(text, reply_markup=markup)

    @router.callback_query(F.data.startswith(ORDERS_PAGE_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def orders_page_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        try:
            page_num = int(str(query.data).split(":")[-1])
        except (ValueError, AttributeError):
            await query.answer("طلب غير صالح.", show_alert=True)
            return
        response = await listing_handler.handle(TelegramCustomerOrderListingInput(
            authenticated_telegram_user_id=user_id,
            page=page_num,
            page_size=ORDER_PAGE_SIZE,
        ))
        await query.answer()
        if not response.ok or response.page is None:
            await query.message.edit_text(render_order_listing_failure(response.message))
            return
        text, markup = render_order_page(response.page)
        await query.message.edit_text(text, reply_markup=markup)

    @router.callback_query(F.data.startswith(ORDER_OPEN_CALLBACK))
    @require_private_callback(msg.DASHBOARD_PRIVATE_ONLY)
    async def open_order_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        code = str(query.data).split(":")[-1]
        ok, error_msg, order = await details_handler.handle(user_id, code)
        if not ok or order is None:
            await query.answer(error_msg, show_alert=True)
            return
        
        await query.answer()
        text, markup = render_order_details(order)
        await query.message.edit_text(text, reply_markup=markup)

    return router
