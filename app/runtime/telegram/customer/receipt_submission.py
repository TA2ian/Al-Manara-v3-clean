"""Customer receipt submission Telegram handler."""
from __future__ import annotations

import uuid
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from app.application.customer_order_details import GetCustomerOrderDetailsCommand
from app.application.submit_receipt import SubmitReceiptCommand
from app.domain.receipt_attempt import ReceiptAttemptStatus, SUPPORTED_RECEIPT_MIME_TYPES
from app.runtime.telegram.shared.guards import get_user_id_from_callback, get_user_id_from_message, require_private_callback, require_private_message


class CustomerReceiptState(StatesGroup):
    awaiting_image = State()


class TelegramReceiptSubmissionHandler:
    def __init__(self, details_service: Any, submission_service: Any) -> None:
        self._details = details_service
        self._submission = submission_service

    async def get_order(self, user_id: int, public_code: str):
        return await self._details.get(GetCustomerOrderDetailsCommand(
            customer_telegram_user_id=user_id,
            public_order_code=public_code,
        ))

    async def submit(self, user_id: int, order_id: uuid.UUID, file_id: str, mime_type: str, idempotency_key: str, image_bytes: bytes = b""):
        return await self._submission.submit(SubmitReceiptCommand(
            order_id=order_id,
            telegram_user_id=user_id,
            telegram_file_id=file_id,
            mime_type=mime_type,
            idempotency_key=idempotency_key,
        ), image_bytes=image_bytes)


def cancel_receipt_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="إلغاء", callback_data="customer:orders")]
    ])


def _render_progress(percent: int, stage: str) -> str:
    filled = int(percent / 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty
    return f"🔄 جاري المعالجة\n\n[{bar}] {percent}%\n{stage}"


from typing import Callable, Awaitable
def build_receipt_submission_router(
    handler: TelegramReceiptSubmissionHandler,
    notify_admins: Callable[[str, Any], Awaitable[None]] | None = None,
) -> Router:
    router = Router(name="customer-receipt-submission")

    @router.callback_query(F.data.startswith("customer:orders:receipt:"))
    @require_private_callback("الإيصال يجب أن يرسل في المحادثة الخاصة.")
    async def begin_receipt(query: CallbackQuery, state: FSMContext) -> None:
        user_id = await get_user_id_from_callback(query)
        if user_id is None:
            return
        
        public_code = str(query.data).split(":")[-1]
        try:
            order = await handler.get_order(user_id, public_code)
        except Exception:
            await query.answer("تعذر جلب تفاصيل الطلب.", show_alert=True)
            return

        if order is None:
            await query.answer("الطلب غير موجود أو لا تملك صلاحية الوصول إليه.", show_alert=True)
            return
            
        if order.status.value != "PENDING_PAYMENT":
            await query.answer("هذا الطلب لا يستقبل إيصالات في حالته الحالية.", show_alert=True)
            return

        await state.clear()
        await state.update_data(
            receipt_order_id=str(order.internal_order_id),
            receipt_public_code=order.public_order_code,
        )
        await state.set_state(CustomerReceiptState.awaiting_image)
        await query.answer()
        await query.message.edit_text(
            f"قم بإرسال صورة الإيصال للطلب {order.public_order_code}.\n"
            "الرجاء إرسال الصورة مباشرة كصورة (وليس كملف PDF).\n\n"
            "ملاحظة: التأكد يتم آلياً، الرجاء التأكد من وضوح الصورة.",
            reply_markup=cancel_receipt_markup()
        )

    @router.message(CustomerReceiptState.awaiting_image, F.photo)
    @require_private_message("الإيصال يجب أن يرسل في المحادثة الخاصة.")
    async def receive_photo(message: Message, state: FSMContext) -> None:
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > 5 * 1024 * 1024:
            await message.answer("❌ الصورة كبيرة جداً. الحد الأقصى للحجم هو 5 ميغابايت.", reply_markup=cancel_receipt_markup())
            return
        await _process_receipt(message, state, handler, "image/jpeg", photo.file_id, notify_admins)

    @router.message(CustomerReceiptState.awaiting_image, F.document)
    @require_private_message("الإيصال يجب أن يرسل في المحادثة الخاصة.")
    async def receive_document(message: Message, state: FSMContext) -> None:
        doc = message.document
        if not doc:
            return
        if doc.file_size and doc.file_size > 5 * 1024 * 1024:
            await message.answer("❌ الصورة كبيرة جداً. الحد الأقصى للحجم هو 5 ميغابايت.", reply_markup=cancel_receipt_markup())
            return
        mime = (doc.mime_type or "").strip().lower()
        if mime == "application/pdf":
            await message.answer("نعتذر، لا ندعم ملفات PDF. الرجاء أخذ لقطة شاشة للإيصال وإرسالها كصورة.", reply_markup=cancel_receipt_markup())
            return
        if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            await message.answer("صيغة الملف غير مدعومة. الرجاء إرسال صورة بصيغة JPEG أو PNG.", reply_markup=cancel_receipt_markup())
            return
        await _process_receipt(message, state, handler, mime, doc.file_id, notify_admins)

    @router.message(CustomerReceiptState.awaiting_image)
    @require_private_message("الإيصال يجب أن يرسل في المحادثة الخاصة.")
    async def reject_invalid_input(message: Message) -> None:
        await message.answer("الرجاء إرسال صورة الإيصال فقط.", reply_markup=cancel_receipt_markup())

    return router


async def _process_receipt(message: Message, state: FSMContext, handler: TelegramReceiptSubmissionHandler, mime: str, file_id: str, notify_admins: Callable[[str, Any], Awaitable[None]] | None = None) -> None:
    user_id = await get_user_id_from_message(message)
    if user_id is None:
        await state.clear()
        return

    data = await state.get_data()
    raw_order_id = data.get("receipt_order_id")
    public_code = str(data.get("receipt_public_code", ""))

    try:
        order_id = uuid.UUID(str(raw_order_id))
    except (TypeError, ValueError):
        await state.clear()
        await message.answer("بيانات الطلب غير صالحة.")
        return

    progress_msg = await message.answer(_render_progress(10, "جارٍ استلام الصورة..."))

    try:
        idempotency_key = f"receipt:{user_id}:{order_id}:{message.message_id}"
        
        await progress_msg.edit_text(_render_progress(20, "جارٍ تنزيل الصورة وفحصها..."))
        
        import io
        stream = io.BytesIO()
        await message.bot.download(file_id, destination=stream)
        image_bytes = stream.getvalue()
        
        await progress_msg.edit_text(_render_progress(40, "جارٍ المعالجة (OCR)..."))
        
        result = await handler.submit(
            user_id=user_id,
            order_id=order_id,
            file_id=file_id,
            mime_type=mime,
            idempotency_key=idempotency_key,
            image_bytes=image_bytes
        )
        
        await progress_msg.edit_text(_render_progress(100, "تمت المعالجة."))
        await state.clear()

        if result.status == ReceiptAttemptStatus.VERIFIED:
            await message.answer(
                f"✅ تم التحقق آليًا من الإيصال للطلب {public_code}.\n"
                "تم تحويل طلبك للإدارة للموافقة النهائية وإرسال الـ USDT."
            )
            # Notify Admins
            if notify_admins:
                await notify_admins(f"🔔 تم رفع إيصال للطلب [{public_code}] والتحقق منه آلياً، بانتظار المراجعة.", message.bot)
        elif result.status == ReceiptAttemptStatus.SUBMITTED:
            await message.answer(
                f"✅ تم استلام الإيصال للطلب {public_code}.\n"
                "الطلب الآن قيد المراجعة اليدوية من قبل الإدارة."
            )
            # Notify Admins
            if notify_admins:
                await notify_admins(f"🔔 الإيصال للطلب [{public_code}] مرفوع وقيد المراجعة.", message.bot)
        else:
            await message.answer("تم حفظ الإيصال، وهو بانتظار مراجعة الإدارة.")
            # Notify Admins
            if notify_admins:
                await notify_admins(f"⚠️ الإيصال للطلب [{public_code}] تم حفظه بحالة {result.status.value}.", message.bot)

    except ValueError as e:
        err = str(e).lower()
        if "size limit" in err:
            await progress_msg.edit_text("❌ الصورة كبيرة جداً.")
        else:
            await progress_msg.edit_text(f"❌ خطأ: {str(e)}")
    except Exception:
        await progress_msg.edit_text("❌ حدث خطأ غير متوقع أثناء معالجة الإيصال. الرجاء المحاولة لاحقاً.")
