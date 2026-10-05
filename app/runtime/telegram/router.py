"""Main Telegram router — assembles all customer and admin sub-routers."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.composition_root import AdminComposition, CustomerComposition
from app.runtime.telegram.admin.dashboard import build_admin_dashboard_router
from app.runtime.telegram.admin.fulfillment import build_fulfillment_router
from app.runtime.telegram.admin.identity_review import build_admin_identity_review_router
from app.runtime.telegram.admin.order_closure import build_admin_order_closure_router
from app.runtime.telegram.admin.order_review import build_admin_order_review_router
from app.runtime.telegram.admin.broadcast import build_admin_broadcast_router
from app.runtime.telegram.admin.super_admin import build_super_admin_router
from app.runtime.telegram.admin.emergency import build_emergency_router
from app.runtime.telegram.customer.dashboard import build_customer_dashboard_router
from app.runtime.telegram.customer.identity import build_customer_identity_router
from app.runtime.telegram.customer.orders import build_customer_orders_router, TelegramCustomerOrderDetailsHandler
from app.runtime.telegram.customer.purchase_order import build_customer_purchase_order_router
from app.runtime.telegram.customer.wallets import build_customer_wallets_router
from app.runtime.telegram.customer.receipt_submission import build_receipt_submission_router, TelegramReceiptSubmissionHandler
from app.runtime.telegram.shared import messages as msg


from app.runtime.telegram.admin.order_review_details import build_admin_order_review_details_router
from app.runtime.telegram.admin.receipt_settings import build_admin_receipt_settings_router
from app.runtime.telegram.admin.payment_accounts import build_admin_payment_accounts_router

def build_admin_router(admin: AdminComposition) -> Router:
    """Assemble all admin-facing routers into a single router."""
    router = Router(name="admin")
    # Emergency router FIRST — must be reachable even during lockdown
    router.include_router(build_emergency_router(admin.user_repository))
    router.include_router(
        build_admin_dashboard_router(admin.identity_review, admin.listing)
    )
    router.include_router(build_admin_identity_review_router(admin.identity_review))
    router.include_router(build_admin_order_review_details_router(admin.review_details))
    router.include_router(build_admin_receipt_settings_router(admin.receipt_settings, admin.identity_review))
    router.include_router(build_admin_payment_accounts_router(admin.payment_accounts, admin.identity_review))
    router.include_router(build_admin_order_review_router(admin.review))
    router.include_router(build_admin_order_closure_router(admin.closure))
    router.include_router(build_fulfillment_router(admin.fulfillment))
    router.include_router(build_admin_broadcast_router(admin.identity_review, admin.user_repository))
    router.include_router(build_super_admin_router(admin.super_admin_service, admin.identity_review))
    return router


def build_customer_router(customer: CustomerComposition) -> Router:
    """Assemble all customer-facing routers into a single router."""
    router = Router(name="customer")
    
    async def notify_admins(message_text: str, bot: Any) -> None:
        try:
            from app.infrastructure.persistence.user_repository import SupabaseUserRepository
            user_repo = SupabaseUserRepository(customer.order_service._customers._client)
            admin_ids = await user_repo.get_admin_telegram_ids()
            for admin_id in admin_ids:
                try:
                    await bot.send_message(admin_id, message_text)
                except Exception:
                    pass
        except Exception:
            pass

    async def is_admin_fn(user_id: int) -> bool:
        try:
            import os
            super_admin = os.environ.get("SUPER_ADMIN_ID")
            if super_admin and str(user_id) == str(super_admin):
                return True
            from app.infrastructure.persistence.user_repository import SupabaseUserRepository
            user_repo = SupabaseUserRepository(customer.order_service._customers._client)
            admin_ids = await user_repo.get_admin_telegram_ids()
            return user_id in admin_ids
        except Exception:
            return False

    router.include_router(build_customer_dashboard_router(is_admin_fn=is_admin_fn))
    router.include_router(build_customer_wallets_router(customer.wallet_handler))
    router.include_router(
        build_customer_purchase_order_router(
            customer.order_service,
            customer.list_wallets_service,
            notify_admins=notify_admins,
        )
    )
    
    details_handler = TelegramCustomerOrderDetailsHandler(customer.order_details)
    router.include_router(build_customer_orders_router(customer.order_listing, details_handler))
    
    receipt_handler = TelegramReceiptSubmissionHandler(customer.order_details, customer.receipt_submission)
    router.include_router(build_receipt_submission_router(receipt_handler, notify_admins=notify_admins))
    
    router.include_router(build_customer_identity_router(customer.identity))

    # Fallback for unknown commands
    fallback = Router(name="customer-navigation")

    @fallback.message(F.text.startswith("/"))
    async def show_unknown_command(message: Message) -> None:
        await message.answer(msg.UNKNOWN_COMMAND)

    router.include_router(fallback)
    return router
