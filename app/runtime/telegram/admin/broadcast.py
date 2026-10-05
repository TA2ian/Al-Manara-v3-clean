"""Admin broadcast handler — /broadcast command."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.guards import get_user_id_from_message, require_private_message
from app.infrastructure.persistence.user_repository import SupabaseUserRepository

logger = logging.getLogger(__name__)


def build_admin_broadcast_router(
    identity_handler: Any,
    user_repository: SupabaseUserRepository,
) -> Router:
    router = Router(name="admin-broadcast")

    async def _authorize(user_id: int) -> Any:
        return await identity_handler.list_pending(user_id)

    @router.message(Command("broadcast"))
    @require_private_message(msg.ADMIN_PRIVATE_ONLY)
    async def admin_broadcast_command(message: Message) -> None:
        user_id = await get_user_id_from_message(message)
        if user_id is None:
            return
            
        auth = await _authorize(user_id)
        if not auth.ok:
            await message.answer(msg.safe(auth.message, msg.ADMIN_UNAUTHORIZED))
            return
            
        # Extract the message text
        command_prefix = "/broadcast"
        text = message.text
        if text:
            text = text[len(command_prefix):].strip()
            
        if not text:
            await message.answer("يرجى كتابة الرسالة بعد الأمر.\nمثال: /broadcast رسالتي هنا")
            return

        await message.answer("جاري إرسال الرسالة إلى جميع المستخدمين...")
        
        try:
            # Fetch all user IDs
            user_ids = await user_repository.get_all_user_telegram_ids()
            success_count = 0
            fail_count = 0
            
            for target_id in user_ids:
                try:
                    await message.bot.send_message(target_id, text)
                    success_count += 1
                except TelegramAPIError as e:
                    logger.warning(f"Failed to send broadcast to {target_id}: {e}")
                    fail_count += 1
                    
            await message.answer(
                f"تم الانتهاء من الإرسال.\n"
                f"✅ نجاح: {success_count}\n"
                f"❌ فشل: {fail_count}"
            )
        except Exception as e:
            logger.error(f"Broadcast failed: {e}", exc_info=True)
            await message.answer(msg.ADMIN_ACTION_FAILED)

    return router
