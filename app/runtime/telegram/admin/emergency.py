"""Emergency lockdown system — /emergency_stop, /emergency_unlock, /transfer_admin.

These commands are secured by the EMERGENCY_SECRET environment variable, NOT by
admin authorization. This means they can be invoked from ANY Telegram account
as long as the secret is correct — a critical safety feature if the admin
account is compromised.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from app.runtime.telegram.shared import messages as msg

logger = logging.getLogger(__name__)

# ─── Global lockdown state ────────────────────────────────────────────────────
# This ContextVar is checked by EmergencyLockdownMiddleware.
# Using a simple module-level bool for cross-request state since the bot
# runs as a single process.
_lockdown_active: bool = False
_lockdown_reason: str = ""


def is_lockdown_active() -> bool:
    """Return whether the bot is in emergency lockdown mode."""
    return _lockdown_active


def get_lockdown_reason() -> str:
    """Return the reason for the current lockdown."""
    return _lockdown_reason


def set_lockdown(active: bool, reason: str = "") -> None:
    """Set the lockdown state globally."""
    global _lockdown_active, _lockdown_reason
    _lockdown_active = active
    _lockdown_reason = reason


def _verify_secret(provided_secret: str) -> bool:
    """Verify the provided secret against the environment variable."""
    expected = os.environ.get("EMERGENCY_SECRET", "").strip()
    if not expected:
        logger.error("EMERGENCY_SECRET is not set in environment variables!")
        return False
    # Constant-time comparison to prevent timing attacks
    import hmac
    return hmac.compare_digest(provided_secret.strip(), expected)


async def _broadcast_emergency_message(
    bot: Any,
    user_repository: Any,
    message_text: str,
) -> tuple[int, int]:
    """Broadcast an emergency message to all users. Returns (success, fail) counts."""
    try:
        user_ids = await user_repository.get_all_user_telegram_ids()
    except Exception:
        logger.error("Failed to fetch user IDs for emergency broadcast.", exc_info=True)
        return 0, 0

    success_count = 0
    fail_count = 0
    for target_id in user_ids:
        try:
            await bot.send_message(target_id, message_text)
            success_count += 1
        except TelegramAPIError:
            fail_count += 1
        # Rate limit: avoid hitting Telegram's broadcast limits
        await asyncio.sleep(0.05)
    return success_count, fail_count


def build_emergency_router(user_repository: Any) -> Router:
    """Build the emergency commands router.

    These commands do NOT use admin authorization — they use the EMERGENCY_SECRET
    environment variable for authentication. This is by design so that the
    commands work even if the admin account is compromised.
    """
    router = Router(name="emergency")

    # ─── /emergency_stop <secret> ────────────────────────────────────────────
    @router.message(Command("emergency_stop"))
    async def emergency_stop_command(message: Message) -> None:
        """Activate emergency lockdown mode."""
        text = message.text or ""
        parts = text.split(maxsplit=1)

        # Extract secret (everything after the command)
        secret = parts[1].strip() if len(parts) > 1 else ""

        if not secret:
            # Don't reveal what this command does — silently ignore
            return

        if not _verify_secret(secret):
            logger.warning(
                "SECURITY: Failed emergency_stop attempt from user %s (id=%s)",
                message.from_user.username if message.from_user else "unknown",
                message.from_user.id if message.from_user else "unknown",
            )
            # Delete the message containing the wrong secret to avoid leaking it
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Delete the message immediately to hide the secret from chat
        try:
            await message.delete()
        except Exception:
            pass

        # Activate lockdown
        invoker_id = message.from_user.id if message.from_user else 0
        invoker_name = message.from_user.username if message.from_user else "unknown"
        set_lockdown(True, f"Emergency stop by @{invoker_name} (ID: {invoker_id})")

        logger.critical(
            "🔴 EMERGENCY LOCKDOWN ACTIVATED by user @%s (ID: %s)",
            invoker_name, invoker_id,
        )

        # Broadcast warning to all users
        success, fail = await _broadcast_emergency_message(
            message.bot,
            user_repository,
            msg.EMERGENCY_WARNING_TO_USERS,
        )

        # Confirm to the invoker via bot.send_message (message.answer fails after delete)
        await message.bot.send_message(
            message.chat.id,
            f"🔴 تم تفعيل وضع الطوارئ بنجاح.\n\n"
            f"• جميع أوامر الإدارة معطلة الآن\n"
            f"• تم تحذير المستخدمين ({success} نجاح / {fail} فشل)\n\n"
            f"لرفع القفل: `/emergency_unlock <secret>`\n"
            f"لنقل الصلاحيات: `/transfer_admin <secret> <new_id>`",
        )

    # ─── /emergency_unlock <secret> ──────────────────────────────────────────
    @router.message(Command("emergency_unlock"))
    async def emergency_unlock_command(message: Message) -> None:
        """Deactivate emergency lockdown mode."""
        text = message.text or ""
        parts = text.split(maxsplit=1)
        secret = parts[1].strip() if len(parts) > 1 else ""

        if not secret:
            return

        if not _verify_secret(secret):
            logger.warning(
                "SECURITY: Failed emergency_unlock attempt from user %s (id=%s)",
                message.from_user.username if message.from_user else "unknown",
                message.from_user.id if message.from_user else "unknown",
            )
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Delete message to hide the secret
        try:
            await message.delete()
        except Exception:
            pass

        if not is_lockdown_active():
            await message.bot.send_message(message.chat.id, "ℹ️ وضع الطوارئ غير مفعل حالياً.")
            return

        # Deactivate lockdown
        invoker_id = message.from_user.id if message.from_user else 0
        invoker_name = message.from_user.username if message.from_user else "unknown"
        set_lockdown(False)

        logger.critical(
            "🟢 EMERGENCY LOCKDOWN DEACTIVATED by user @%s (ID: %s)",
            invoker_name, invoker_id,
        )

        # Broadcast all-clear to users
        success, fail = await _broadcast_emergency_message(
            message.bot,
            user_repository,
            msg.EMERGENCY_RESOLVED_TO_USERS,
        )

        await message.bot.send_message(
            message.chat.id,
            f"🟢 تم رفع وضع الطوارئ بنجاح.\n\n"
            f"• جميع أوامر الإدارة عادت للعمل\n"
            f"• تم إشعار المستخدمين ({success} نجاح / {fail} فشل)",
        )

    # ─── /transfer_admin <secret> <new_telegram_id> ──────────────────────────
    @router.message(Command("transfer_admin"))
    async def transfer_admin_command(message: Message) -> None:
        """Transfer admin privileges to a new Telegram account."""
        text = message.text or ""
        parts = text.split()

        # Expected: /transfer_admin <secret> <new_id>
        if len(parts) < 3:
            return

        secret = parts[1].strip()
        new_id_str = parts[2].strip()

        if not _verify_secret(secret):
            logger.warning(
                "SECURITY: Failed transfer_admin attempt from user %s (id=%s)",
                message.from_user.username if message.from_user else "unknown",
                message.from_user.id if message.from_user else "unknown",
            )
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Delete message to hide the secret
        try:
            await message.delete()
        except Exception:
            pass

        # Validate new admin ID
        try:
            new_admin_id = int(new_id_str)
            if new_admin_id <= 0:
                raise ValueError
        except ValueError:
            await message.bot.send_message(message.chat.id, "❌ معرف Telegram الجديد غير صالح. يجب أن يكون رقماً صحيحاً موجباً.")
            return

        # Perform the transfer via Supabase RPC
        try:
            import asyncio
            response = await asyncio.to_thread(
                user_repository._client.rpc(
                    "emergency_transfer_admin",
                    {"p_new_admin_telegram_id": new_admin_id},
                ).execute
            )
            success = bool(getattr(response, "data", False))
        except Exception:
            logger.error("Failed to transfer admin via RPC", exc_info=True)
            success = False

        invoker_id = message.from_user.id if message.from_user else 0
        invoker_name = message.from_user.username if message.from_user else "unknown"

        if success:
            logger.critical(
                "🔄 ADMIN TRANSFERRED from old admin to new ID %s by @%s (ID: %s)",
                new_admin_id, invoker_name, invoker_id,
            )

            # Notify all users
            await _broadcast_emergency_message(
                message.bot,
                user_repository,
                msg.EMERGENCY_ADMIN_TRANSFERRED_TO_USERS,
            )

            # Notify the new admin
            try:
                await message.bot.send_message(
                    new_admin_id,
                    "🔑 تم نقل صلاحيات إدارة بوت المنارة إليك.\n"
                    "استخدم /admin للوصول إلى لوحة التحكم.",
                )
            except TelegramAPIError:
                logger.warning("Could not notify new admin ID %s", new_admin_id)

            await message.bot.send_message(
                message.chat.id,
                f"🔄 تم نقل صلاحيات الإدارة إلى المعرف الجديد ({new_admin_id}) بنجاح.\n\n"
                f"الحساب القديم لم يعد يملك صلاحيات الإدارة.",
            )
        else:
            await message.bot.send_message(message.chat.id, msg.ADMIN_ACTION_FAILED)

    return router
