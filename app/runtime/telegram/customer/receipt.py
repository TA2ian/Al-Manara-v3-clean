"""Customer receipt submission Telegram handler."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.application.submit_receipt import SubmitReceiptCommand, SubmitReceiptService
from app.domain.receipt_attempt import SUPPORTED_RECEIPT_MIME_TYPES
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id

RECEIPT_ORDER_KEY = "receipt_order_id"


class ReceiptStates(StatesGroup):
    waiting_for_image = State()


@dataclass(frozen=True, slots=True)
class TelegramReceiptInput:
    user_id: int
    order_id: UUID
    telegram_file_id: str
    mime_type: str
    idempotency_key: str


def _telegram_mime_for_photo() -> str:
    """Telegram photo objects are always JPEG."""
    return "image/jpeg"


def _mime_for_document(mime_type: str | None) -> str | None:
    """Return normalized MIME if supported, else None."""
    if mime_type in SUPPORTED_RECEIPT_MIME_TYPES:
        return mime_type
    return None


def build_customer_receipt_router(
    service: SubmitReceiptService,
) -> Router:
    """Router that handles receipt image submission for an active order.

    To enter this flow the caller must put the order UUID in FSM state
    under the key ``RECEIPT_ORDER_KEY`` and set ``ReceiptStates.waiting_for_image``.
    """
    router = Router(name="customer-receipt")

    async def _handle_receipt(message: Message, state: FSMContext, file_id: str, mime: str) -> None:
        data = await state.get_data()
        order_id_str = data.get(RECEIPT_ORDER_KEY)
        if not order_id_str:
            await message.answer(msg.RECEIPT_ERROR)
            await state.clear()
            return
        try:
            order_id = UUID(order_id_str)
        except ValueError:
            await message.answer(msg.RECEIPT_ERROR)
            await state.clear()
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer(msg.IDENTITY_CHECK_FAILED)
            await state.clear()
            return
        try:
            await service.submit(SubmitReceiptCommand(
                order_id=order_id,
                telegram_user_id=user_id,
                telegram_file_id=file_id,
                mime_type=mime,
                idempotency_key=str(uuid4()),
            ))
            await state.clear()
            await message.answer(msg.RECEIPT_ACCEPTED)
        except ValueError:
            await state.clear()
            await message.answer(msg.RECEIPT_FAILED)
        except Exception:
            await state.clear()
            await message.answer(msg.RECEIPT_ERROR)

    @router.message(ReceiptStates.waiting_for_image, F.photo)
    async def handle_photo(message: Message, state: FSMContext) -> None:
        # Largest photo size
        photo = message.photo[-1]
        await _handle_receipt(message, state, photo.file_id, _telegram_mime_for_photo())

    @router.message(ReceiptStates.waiting_for_image, F.document)
    async def handle_document(message: Message, state: FSMContext) -> None:
        doc = message.document
        if doc is None:
            await message.answer(msg.RECEIPT_INVALID)
            return
        mime = _mime_for_document(doc.mime_type)
        if mime is None:
            await message.answer(msg.RECEIPT_PROMPT)
            return
        await _handle_receipt(message, state, doc.file_id, mime)

    @router.message(ReceiptStates.waiting_for_image)
    async def handle_non_image(message: Message, state: FSMContext) -> None:
        """User sent something other than a photo or document."""
        await message.answer(msg.RECEIPT_PROMPT)

    return router
