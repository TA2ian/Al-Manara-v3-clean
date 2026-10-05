"""Guard decorators that eliminate repeated private-chat + auth checks in every handler."""
from __future__ import annotations

import functools
from typing import Any, Callable, Coroutine

from aiogram.types import CallbackQuery, Message

from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message
from app.runtime.telegram.shared import messages as msg


def require_private_message(
    fallback: str = msg.PRIVATE_ONLY,
) -> Callable[[Callable[..., Coroutine[Any, Any, None]]], Callable[..., Coroutine[Any, Any, None]]]:
    """Decorator: reply with *fallback* and return early if the message is not private."""

    def decorator(func: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., Coroutine[Any, Any, None]]:
        @functools.wraps(func)
        async def wrapper(message: Message, *args: Any, **kwargs: Any) -> None:
            if not is_private_message(message):
                await message.answer(fallback)
                return
            await func(message, *args, **kwargs)

        return wrapper

    return decorator


def require_private_callback(
    fallback: str = msg.PRIVATE_ONLY,
) -> Callable[[Callable[..., Coroutine[Any, Any, None]]], Callable[..., Coroutine[Any, Any, None]]]:
    """Decorator: answer with *fallback* alert and return early for non-private callback queries."""

    def decorator(func: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., Coroutine[Any, Any, None]]:
        @functools.wraps(func)
        async def wrapper(query: CallbackQuery, *args: Any, **kwargs: Any) -> None:
            if query.message is None or not is_private_message(query.message):
                await query.answer(fallback, show_alert=True)
                return
            await func(query, *args, **kwargs)

        return wrapper

    return decorator


async def get_user_id_from_message(message: Message) -> int | None:
    """Extract and return authenticated user id or send error reply."""
    user_id = authenticated_telegram_user_id(message)
    if user_id is None:
        await message.answer(msg.IDENTITY_CHECK_FAILED)
    return user_id


async def get_user_id_from_callback(query: CallbackQuery) -> int | None:
    """Extract and return authenticated user id or answer with error alert."""
    user_id = authenticated_telegram_user_id(query)
    if user_id is None:
        await query.answer(msg.IDENTITY_CHECK_FAILED, show_alert=True)
    return user_id
