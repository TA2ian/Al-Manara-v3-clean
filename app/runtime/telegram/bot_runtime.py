"""Production aiogram polling runtime — cross-platform (Linux and Windows)."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, ErrorEvent
from supabase import create_client

from app.composition_root import build_admin_composition, build_customer_composition
from app.runtime.telegram.router import build_admin_router, build_customer_router
from app.runtime.telegram.shared.i18n import I18nService
import app.runtime.telegram.shared.i18n as i18n_module
from app.runtime.telegram.shared.middlewares import RateLimitMiddleware, UserMiddleware, EmergencyLockdownMiddleware
from app.application.user_management import UserManagementService
from app.infrastructure.persistence.user_repository import SupabaseUserRepository

POLLING_UPDATE_TYPES = ("message", "callback_query")
LEASE_DURATION_SECONDS = 60
LEASE_RENEWAL_INTERVAL_SECONDS = 15
LEASE_RPC_TIMEOUT_SECONDS = 10
LOGGER = logging.getLogger(__name__)


# ─── Settings ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class TelegramBotSettings:
    token: str
    supabase_url: str
    supabase_service_role_key: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "TelegramBotSettings":
        values = environment if environment is not None else os.environ
        required = {
            "TELEGRAM_BOT_TOKEN": values.get("TELEGRAM_BOT_TOKEN", "").strip(),
            "SUPABASE_URL": values.get("SUPABASE_URL", "").strip(),
            "SUPABASE_SERVICE_ROLE_KEY": values.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing required bot configuration: {', '.join(missing)}")
        return cls(
            token=required["TELEGRAM_BOT_TOKEN"],
            supabase_url=required["SUPABASE_URL"],
            supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        )


# ─── OS-level single-poller lock (cross-platform) ─────────────────────────────

class SinglePollerLock:
    """Cross-platform exclusive lock that prevents duplicate pollers on one host.

    On Linux/macOS uses ``fcntl`` (POSIX file locking).
    On Windows uses a named mutex via ``msvcrt.locking``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(tempfile.gettempdir()) / "al-manara-v3-telegram.lock"
        self._handle = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def _acquire_posix(self) -> bool:
        import fcntl
        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return True

    def _acquire_windows(self) -> bool:
        import msvcrt
        try:
            handle = self._path.open("a+b")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            self._handle = handle
            return True
        except OSError:
            return False

    def release(self) -> None:
        if self._handle is None:
            return
        if sys.platform == "win32":
            import msvcrt
            try:
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


# ─── Shared Supabase polling lease ────────────────────────────────────────────

class SharedPollerLease(Protocol):
    async def acquire(self) -> bool: ...
    async def renew(self) -> bool: ...
    async def release(self) -> bool: ...


class SharedPollerLeaseError(RuntimeError):
    """The shared lease store could not confirm ownership."""


class SharedPollerLeaseUnavailable(RuntimeError):
    """Another healthy host currently owns the customer poller lease."""


class SupabaseSharedPollerLease:
    """Supabase RPC adapter for the customer Telegram polling lease."""

    def __init__(
        self,
        client: Any,
        *,
        owner_id: UUID | None = None,
        lease_seconds: int = LEASE_DURATION_SECONDS,
        rpc_timeout_seconds: float = LEASE_RPC_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._owner_id = owner_id or uuid4()
        self._lease_seconds = lease_seconds
        self._rpc_timeout_seconds = rpc_timeout_seconds

    async def acquire(self) -> bool:
        return await self._call("acquire_telegram_poller_lease", "acquired")

    async def renew(self) -> bool:
        return await self._call("renew_telegram_poller_lease", "renewed")

    async def release(self) -> bool:
        return await self._call("release_telegram_poller_lease", "released")

    async def _call(self, function_name: str, result_name: str) -> bool:
        params: dict[str, object] = {"p_owner_id": str(self._owner_id)}
        if function_name != "release_telegram_poller_lease":
            params["p_lease_seconds"] = self._lease_seconds
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._client.rpc(function_name, params).execute),
                timeout=self._rpc_timeout_seconds,
            )
        except Exception as exc:
            raise SharedPollerLeaseError("shared poller lease RPC failed") from exc
        if getattr(response, "error", None):
            raise SharedPollerLeaseError("shared poller lease RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise SharedPollerLeaseError("shared poller lease RPC returned invalid data")

        row = data[0]
        val = row.get(result_name)
        if not isinstance(val, bool):
            for v in row.values():
                if isinstance(v, bool):
                    val = v
                    break
        if not isinstance(val, bool):
            raise SharedPollerLeaseError("shared poller lease RPC returned invalid data")
        return val


def build_shared_poller_lease(settings: TelegramBotSettings) -> SharedPollerLease:
    return SupabaseSharedPollerLease(
        create_client(settings.supabase_url, settings.supabase_service_role_key)
    )


# ─── Error handler ────────────────────────────────────────────────────────────

async def log_telegram_error(event: ErrorEvent) -> bool:
    del event
    LOGGER.error("Unhandled Telegram update error.")
    return True


# ─── Runtime builder ──────────────────────────────────────────────────────────

def build_telegram_runtime(settings: TelegramBotSettings) -> tuple[Bot, Dispatcher]:
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    
    # Initialize i18n
    locale_dir = Path(__file__).parent / "locales"
    i18n_module.i18n_instance = I18nService(str(locale_dir))
    
    admin = build_admin_composition(client)
    customer = build_customer_composition(client)
    dispatcher = Dispatcher()
    
    # Register middlewares globally
    # Emergency lockdown middleware FIRST — blocks admin ops before anything else
    dispatcher.message.middleware(EmergencyLockdownMiddleware())
    dispatcher.callback_query.middleware(EmergencyLockdownMiddleware())
    
    user_repo = SupabaseUserRepository(client)
    user_management_service = UserManagementService(user_repo)
    dispatcher.message.middleware(RateLimitMiddleware(limit=5, window=2))
    dispatcher.callback_query.middleware(RateLimitMiddleware(limit=10, window=2))
    dispatcher.message.middleware(UserMiddleware(user_management_service))
    dispatcher.callback_query.middleware(UserMiddleware(user_management_service))

    dispatcher.include_router(build_admin_router(admin))
    dispatcher.include_router(build_customer_router(customer))
    dispatcher.errors.register(log_telegram_error)
    return Bot(token=settings.token), dispatcher


# ─── Lease renewal task ───────────────────────────────────────────────────────

async def _renew_lease_until_stopped(
    lease: SharedPollerLease,
    dispatcher: Dispatcher,
    renewal_interval_seconds: float,
    renewal_timeout_seconds: float,
) -> None:
    consecutive_failures = 0
    max_retries = 3
    while True:
        await asyncio.sleep(renewal_interval_seconds)
        try:
            renewed = await asyncio.wait_for(lease.renew(), timeout=renewal_timeout_seconds)
            if renewed:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
        except Exception as exc:
            consecutive_failures += 1
            LOGGER.warning("Lease renewal attempt failed (%d/%d): %s", consecutive_failures, max_retries, exc)

        if consecutive_failures >= max_retries:
            LOGGER.error("Shared Telegram poller lease was lost after %d consecutive failed renewals; stopping polling.", max_retries)
            await dispatcher.stop_polling()
            return


# ─── Main polling coroutine ───────────────────────────────────────────────────

async def run_polling(
    settings: TelegramBotSettings,
    lease: SharedPollerLease | None = None,
    *,
    renewal_interval_seconds: float = LEASE_RENEWAL_INTERVAL_SECONDS,
    renewal_timeout_seconds: float = LEASE_RPC_TIMEOUT_SECONDS,
) -> None:
    if renewal_interval_seconds <= 0 or renewal_timeout_seconds <= 0:
        raise ValueError("lease renewal interval and timeout must be positive")
    if renewal_interval_seconds + renewal_timeout_seconds >= LEASE_DURATION_SECONDS:
        raise ValueError("lease renewal must fail before the lease can expire")

    shared_lease = lease or build_shared_poller_lease(settings)
    if not await shared_lease.acquire():
        raise SharedPollerLeaseUnavailable("another host owns the Telegram poller lease")

    bot: Bot | None = None
    renew_task: asyncio.Task[None] | None = None
    try:
        bot, dispatcher = build_telegram_runtime(settings)
        renew_task = asyncio.create_task(
            _renew_lease_until_stopped(
                shared_lease,
                dispatcher,
                renewal_interval_seconds,
                renewal_timeout_seconds,
            )
        )
        await bot.delete_webhook(drop_pending_updates=False)
        identity = await bot.get_me()
        bot._me = identity
        await bot.set_my_commands([
            BotCommand(command="start", description="فتح لوحة المنارة"),
            BotCommand(command="verify", description="إرسال بيانات التحقق"),
            BotCommand(command="wallets", description="إدارة محافظ USDT"),
            BotCommand(command="buy", description="إنشاء طلب شراء"),
            BotCommand(command="orders", description="عرض طلباتك"),
        ])
        LOGGER.info("Telegram polling transport is ready for bot id %s.", identity.id)
        await dispatcher.start_polling(bot, allowed_updates=POLLING_UPDATE_TYPES)
    finally:
        if renew_task is not None:
            renew_task.cancel()
            await asyncio.gather(renew_task, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        try:
            await shared_lease.release()
        except SharedPollerLeaseError:
            LOGGER.error("Unable to release the shared Telegram poller lease.")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main(lock: SinglePollerLock | None = None) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    poller_lock = lock or SinglePollerLock()
    if not poller_lock.acquire():
        LOGGER.error("Telegram bot is already running on this host; refusing a second poller.")
        raise SystemExit(1)
    try:
        LOGGER.info("Starting Telegram polling service.")
        asyncio.run(run_polling(TelegramBotSettings.from_environment()))
    except Exception:
        LOGGER.exception("Telegram bot stopped because startup or polling failed.")
        raise SystemExit(1) from None
    finally:
        poller_lock.release()
