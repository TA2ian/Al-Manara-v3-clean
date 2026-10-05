from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.application.user_management import UserManagementService
from app.runtime.telegram.shared import messages as msg
from app.runtime.telegram.shared.i18n import current_lang

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """
    Middleware to handle user preferences and misconduct checks.
    Sets the current_lang contextvar for i18n, checks if the user is suspended,
    and updates the user's information in the database.
    """
    def __init__(self, user_management_service: UserManagementService):
        self.user_management_service = user_management_service
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract user ID and language from the event
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        try:
            # Sync user and get their state
            user_state = await self.user_management_service.get_or_create_user(
                telegram_id=user.id,
                username=user.username,
                language_code=user.language_code or "ar",
            )
            
            # Set the language context variable
            lang_token = current_lang.set(user_state.language_code)

            try:
                # Check suspension
                if user_state.suspended_until:
                    if isinstance(event, Message):
                        await event.answer(
                            msg.USER_SUSPENDED.format(suspended_until=user_state.suspended_until.isoformat())
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer(
                            msg.USER_SUSPENDED.format(suspended_until=user_state.suspended_until.isoformat()),
                            show_alert=True
                        )
                    return # Block execution
                
                # If not suspended, proceed to handler
                return await handler(event, data)
            finally:
                # Reset language contextvar (not strictly necessary per-request in some async frameworks, but good practice)
                current_lang.reset(lang_token)

        except Exception as e:
            logger.error(f"Error in UserMiddleware: {e}", exc_info=True)
            # In case of DB failure, default to Arabic and proceed so bot isn't completely dead
            lang_token = current_lang.set("ar")
            try:
                return await handler(event, data)
            finally:
                current_lang.reset(lang_token)


class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware to prevent spam/flooding by rate-limiting users.
    If a user sends more than `limit` messages per `window` seconds,
    they are ignored. This operates in-memory.
    """
    def __init__(self, limit: int = 5, window: int = 2):
        self.limit = limit
        self.window = window
        self._user_requests: dict[int, list[float]] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        now = time.time()
        
        # Initialize or get user requests
        requests = self._user_requests.get(user_id, [])
        
        # Filter requests within the window
        requests = [req_time for req_time in requests if now - req_time < self.window]
        
        if len(requests) >= self.limit:
            # Rate limit exceeded. Silently drop the update.
            logger.warning(f"User {user_id} is being rate-limited.")
            return

        # Add current request and update dict
        requests.append(now)
        self._user_requests[user_id] = requests

        return await handler(event, data)


class EmergencyLockdownMiddleware(BaseMiddleware):
    """Middleware that blocks admin operations when emergency lockdown is active.

    During lockdown:
    - Emergency commands (/emergency_stop, /emergency_unlock, /transfer_admin) are ALWAYS allowed.
    - Regular user commands (/start, /verify, /wallets, /buy, /orders) are allowed.
    - ALL admin commands and callbacks (starting with "admin:") are BLOCKED.
    """

    # Commands that are always allowed even during lockdown
    EMERGENCY_COMMANDS = frozenset({"emergency_stop", "emergency_unlock", "transfer_admin"})
    USER_COMMANDS = frozenset({"start", "verify", "wallets", "buy", "orders"})

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from app.runtime.telegram.admin.emergency import is_lockdown_active

        if not is_lockdown_active():
            return await handler(event, data)

        # Lockdown is active — decide what to allow
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/"):
                command = text.split()[0].lstrip("/").split("@")[0].lower()
                # Always allow emergency commands
                if command in self.EMERGENCY_COMMANDS:
                    return await handler(event, data)
                # Allow regular user commands
                if command in self.USER_COMMANDS:
                    return await handler(event, data)
                # Block admin commands
                if command in ("admin", "broadcast"):
                    await event.answer(
                        "🔴 النظام في وضع الطوارئ حالياً.\n"
                        "جميع عمليات الإدارة معطلة مؤقتاً حتى رفع حالة الطوارئ."
                    )
                    return
            # Allow non-command messages (user input during FSM states, etc.)
            return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            callback_data = getattr(event, "data", "") or ""
            # Block all admin callbacks during lockdown
            if callback_data.startswith("admin:"):
                await event.answer(
                    "🔴 النظام في وضع الطوارئ. جميع عمليات الإدارة معطلة.",
                    show_alert=True,
                )
                return
            # Allow customer callbacks
            return await handler(event, data)

        return await handler(event, data)
