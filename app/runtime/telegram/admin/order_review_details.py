"""Admin order review details Telegram handler."""
from __future__ import annotations

import uuid
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.application.admin_order_review_details import GetAdminOrderReviewDetailsCommand
from app.runtime.telegram.admin.order_review import order_action_markup
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_callback, require_private_callback


class TelegramAdminOrderReviewDetailsHandler:
    def __init__(self, details_service: Any) -> None:
        self._service = details_service

    async def handle(self, admin_user_id: int, order_id_str: str):
        try:
            order_id = uuid.UUID(order_id_str)
            details = await self._service.get(GetAdminOrderReviewDetailsCommand(
                admin_user_id=admin_user_id,
                actor_type="primary",
                order_id=order_id,
            ))
            return True, "", details
        except ValueError as e:
            return False, str(e), None
        except Exception:
            return False, "تعذر جلب تفاصيل الطلب.", None


def build_admin_order_review_details_router(
    handler: TelegramAdminOrderReviewDetailsHandler,
) -> Router:
    router = Router(name="admin-order-review-details")

    @router.callback_query(F.data.startswith("admin:order:details:"))
    @require_private_callback(msg.ADMIN_PRIVATE_ONLY)
    async def view_order_details_callback(query: CallbackQuery) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
            
        order_id_str = str(query.data).split(":")[-1]
        ok, error_msg, details = await handler.handle(user_id, order_id_str)
        
        if not ok or details is None:
            await query.answer(error_msg, show_alert=True)
            return

        await query.answer()

        lines = [
            f"📋 تفاصيل الطلب للمراجعة: {details.public_order_code}",
            "─" * 20,
            f"الحالة: {details.status}",
            f"معرف العميل: {details.user_telegram_id}",
            f"المبلغ: {details.requested_amount} USDT",
            f"المبلغ المحلي الواجب دفعه: {details.local_amount} {details.payment_currency}",
            f"الشبكة: {details.network_code}",
            "",
        ]
        
        receipt = details.latest_receipt
        has_image = False
        
        if receipt:
            lines.append(f"📄 الإيصال المرفق (محاولة رقم {receipt.attempt_number}):")
            lines.append(f"حالة الإيصال: {receipt.processing_status}")
            lines.append(f"تاريخ الرفع: {receipt.submitted_at.strftime('%Y-%m-%d %H:%M')}")
            if receipt.telegram_file_id:
                has_image = True
        else:
            lines.append("❌ لا يوجد إيصال مرفوع لهذا الطلب بعد.")

        text = "\n".join(lines)
        
        # Add approval/rejection markup if it's UNDER_REVIEW
        markup = None
        if details.status == "UNDER_REVIEW":
            markup = order_action_markup(details.internal_order_id, details.version)
        else:
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 عودة", callback_data="admin:review_orders")
            ]])

        if has_image and receipt and receipt.telegram_file_id:
            await query.message.answer_photo(
                photo=receipt.telegram_file_id,
                caption=text,
                reply_markup=markup
            )
        else:
            await query.message.answer(text, reply_markup=markup)

    return router
