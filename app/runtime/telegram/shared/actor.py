"""Shared actor utilities — extract authenticated identity from Telegram events."""
from __future__ import annotations

from aiogram.types import CallbackQuery, Message


def authenticated_telegram_user_id(
    message_or_callback: Message | CallbackQuery,
) -> int | None:
    """Return Telegram's authenticated sender identity, never callback data."""
    user_id = getattr(message_or_callback.from_user, "id", None)
    return user_id if isinstance(user_id, int) and user_id > 0 else None


def is_private_message(message: Message) -> bool:
    """Return True only when the chat is a private DM with the bot."""
    return getattr(message.chat, "type", None) == "private"
