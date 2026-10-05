"""Clean composition root — wires all dependencies for admin and customer runtimes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.application.admin_order_closure import AdminOrderClosureService
from app.application.admin_order_listing import AdminOrderListingService
from app.application.admin_order_review import AdminOrderReviewService
from app.application.create_purchase_order import CreatePurchaseOrderService
from app.application.customer_identity import CustomerIdentityService
from app.application.customer_order_listing import CustomerOrderListingService
from app.application.disable_wallet import DisableWalletService
from app.application.fulfillment import FulfillmentService
from app.application.list_wallets import ListWalletsService
from app.application.order_service import OrderTransitionService
from app.application.register_wallet import RegisterWalletService
from app.application.super_admin_service import SuperAdminService
from app.application.uow import UnitOfWork
from app.infrastructure.persistence.admin_authorization_repository import SupabaseAdminAuthorizationRepository
from app.infrastructure.persistence.admin_order_closure_repository import SupabaseAdminOrderClosureRepository
from app.infrastructure.persistence.admin_order_listing_repository import SupabaseAdminOrderListingRepository
from app.infrastructure.persistence.audit_logger import SupabaseAuditLogger
from app.infrastructure.persistence.customer_identity_repository import SupabaseCustomerIdentityRepository
from app.infrastructure.persistence.customer_order_listing_repository import SupabaseCustomerOrderListingRepository
from app.infrastructure.persistence.fulfillment_repository import SupabaseFulfillmentRepository
from app.infrastructure.persistence.order_creation_repository import SupabaseOrderCreationRepository
from app.infrastructure.persistence.order_support_repositories import (
    SupabaseCustomerRepository,
    SupabaseNetworkOrderRepository,
    SupabasePaymentSettingsRepository,
)
from app.infrastructure.persistence.quote_support_repository import (
    SupabaseExchangeRateProvider,
    SupabaseFeePolicyProvider,
    SupabaseRoundingPolicyProvider,
    UtcQuoteClock,
    UuidPublicOrderCodeGenerator,
)
from app.infrastructure.persistence.supabase_order_uow import SupabaseOrderUnitOfWork
from app.infrastructure.persistence.wallet_repository import SupabaseWalletRepository
from app.infrastructure.persistence.user_repository import SupabaseUserRepository
from app.infrastructure.persistence.admin_super_tools_repository import SupabaseAdminSuperToolsRepository
from app.runtime.telegram.admin.fulfillment import TelegramFulfillmentHandler
from app.runtime.telegram.admin.identity_review import TelegramAdminCustomerIdentityHandler
from app.runtime.telegram.admin.order_closure import TelegramAdminOrderClosureHandler
from app.runtime.telegram.admin.order_listing import TelegramAdminOrderListingHandler
from app.runtime.telegram.admin.order_review import TelegramAdminOrderReviewHandler
from app.runtime.telegram.customer.identity import TelegramCustomerIdentityHandler
from app.runtime.telegram.customer.orders import TelegramCustomerOrderListingHandler
from app.runtime.telegram.customer.wallets import TelegramWalletHandler


@dataclass(frozen=True, slots=True)
class AdminComposition:
    """Fully wired admin runtime slices."""

    review: TelegramAdminOrderReviewHandler
    listing: TelegramAdminOrderListingHandler
    closure: TelegramAdminOrderClosureHandler
    fulfillment: TelegramFulfillmentHandler
    identity_review: TelegramAdminCustomerIdentityHandler
    user_repository: Any  # SupabaseUserRepository
    super_admin_service: SuperAdminService
    review_details: Any
    receipt_settings: Any
    payment_accounts: Any


@dataclass(frozen=True, slots=True)
class CustomerComposition:
    """Fully wired customer runtime slices."""

    order_service: CreatePurchaseOrderService
    wallet_handler: TelegramWalletHandler
    order_listing: TelegramCustomerOrderListingHandler
    identity: TelegramCustomerIdentityHandler
    list_wallets_service: ListWalletsService
    order_details: Any
    receipt_submission: Any


from app.application.admin_order_review_details import AdminOrderReviewDetailsService
from app.infrastructure.persistence.admin_order_review_details_repository import SupabaseAdminOrderReviewDetailsRepository
from app.runtime.telegram.admin.order_review_details import TelegramAdminOrderReviewDetailsHandler
from app.application.admin_receipt_settings import AdminReceiptSettingsService
from app.infrastructure.persistence.admin_receipt_settings_repository import SupabaseAdminReceiptSettingsRepository
from app.runtime.telegram.admin.receipt_settings import TelegramAdminReceiptSettingsHandler

from app.application.admin_payment_account import AdminPaymentAccountService
from app.infrastructure.persistence.admin_payment_account_repository import SupabaseAdminPaymentAccountRepository
from app.runtime.telegram.admin.payment_accounts import TelegramAdminPaymentAccountHandler

def build_admin_composition(client: Any, order_uow: UnitOfWork | None = None) -> AdminComposition:
    authorization = SupabaseAdminAuthorizationRepository(client)
    transitions = OrderTransitionService(order_uow or SupabaseOrderUnitOfWork(client))
    review_service = AdminOrderReviewService(transitions, authorization)
    listing_service = AdminOrderListingService(SupabaseAdminOrderListingRepository(client))
    closure_service = AdminOrderClosureService(SupabaseAdminOrderClosureRepository(client))
    fulfillment_service = FulfillmentService(SupabaseFulfillmentRepository(client))
    identity_service = CustomerIdentityService(SupabaseCustomerIdentityRepository(client))
    user_repo = SupabaseUserRepository(client)
    super_tools_repo = SupabaseAdminSuperToolsRepository(client)
    super_admin_service = SuperAdminService(super_tools_repo, user_repo, authorization)
    
    review_details_service = AdminOrderReviewDetailsService(SupabaseAdminOrderReviewDetailsRepository(client))
    receipt_settings_service = AdminReceiptSettingsService(SupabaseAdminReceiptSettingsRepository(client))
    payment_accounts_service = AdminPaymentAccountService(SupabaseAdminPaymentAccountRepository(client))

    return AdminComposition(
        review=TelegramAdminOrderReviewHandler(review_service),
        listing=TelegramAdminOrderListingHandler(listing_service),
        closure=TelegramAdminOrderClosureHandler(closure_service),
        fulfillment=TelegramFulfillmentHandler(fulfillment_service),
        identity_review=TelegramAdminCustomerIdentityHandler(identity_service),
        user_repository=user_repo,
        super_admin_service=super_admin_service,
        review_details=TelegramAdminOrderReviewDetailsHandler(review_details_service),
        receipt_settings=TelegramAdminReceiptSettingsHandler(receipt_settings_service),
        payment_accounts=TelegramAdminPaymentAccountHandler(payment_accounts_service),
    )


from app.application.customer_order_details import CustomerOrderDetailsService
from app.infrastructure.persistence.customer_order_details_repository import SupabaseCustomerOrderDetailsRepository
from app.application.submit_customer_receipt import SubmitCustomerReceiptService
from app.infrastructure.persistence.receipt_attempt_repository import SupabaseReceiptAttemptRepository

class SimpleUtcClock:
    def now(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)

def build_customer_composition(client: Any) -> CustomerComposition:
    wallet_repository = SupabaseWalletRepository(client)
    list_wallets_service = ListWalletsService(wallet_repository)
    order_service = CreatePurchaseOrderService(
        customers=SupabaseCustomerRepository(client),
        wallets=wallet_repository,
        networks=SupabaseNetworkOrderRepository(client),
        payments=SupabasePaymentSettingsRepository(client),
        orders=SupabaseOrderCreationRepository(client),
        public_codes=UuidPublicOrderCodeGenerator(),
        exchange_rates=SupabaseExchangeRateProvider(client),
        fee_policies=SupabaseFeePolicyProvider(client),
        rounding_policies=SupabaseRoundingPolicyProvider(client),
        clock=UtcQuoteClock(),
        quote_ttl=timedelta(minutes=10),
    )
    wallet_handler = TelegramWalletHandler(
        listing=list_wallets_service,
        registration=RegisterWalletService(wallet_repository),
        disabling=DisableWalletService(wallet_repository, SupabaseAuditLogger(client)),
    )
    
    order_details_service = CustomerOrderDetailsService(SupabaseCustomerOrderDetailsRepository(client))
    
    from app.application.receipt_image import ReceiptImageInspectorImpl
    from app.application.receipt_image_normalizer import ReceiptImageNormalizer
    from app.infrastructure.local_tesseract_ocr import LocalTesseractOcrAdapter
    from app.application.receipt_verification_service import ReceiptFinancialVerificationService
    from app.application.receipt_orchestrator import ReceiptSubmissionOrchestrator
    from app.infrastructure.persistence.order_verification_snapshot_repository import SupabaseOrderVerificationSnapshotRepository

    attempts_repo = SupabaseReceiptAttemptRepository(client)
    inspector = ReceiptImageInspectorImpl()
    normalizer = ReceiptImageNormalizer()
    ocr = LocalTesseractOcrAdapter()
    snapshot_reader = SupabaseOrderVerificationSnapshotRepository(client)
    verification = ReceiptFinancialVerificationService(snapshots=snapshot_reader)

    orchestrator = ReceiptSubmissionOrchestrator(
        inspector=inspector,
        normalizer=normalizer,
        ocr=ocr,
        verification=verification,
        finalizer=attempts_repo
    )

    receipt_submission_service = SubmitCustomerReceiptService(
        attempts=attempts_repo,
        inspector=inspector,
        clock=SimpleUtcClock(),
        orchestrator=orchestrator
    )
    
    return CustomerComposition(
        order_service=order_service,
        wallet_handler=wallet_handler,
        order_listing=TelegramCustomerOrderListingHandler(
            CustomerOrderListingService(SupabaseCustomerOrderListingRepository(client))
        ),
        identity=TelegramCustomerIdentityHandler(
            CustomerIdentityService(SupabaseCustomerIdentityRepository(client))
        ),
        list_wallets_service=list_wallets_service,
        order_details=order_details_service,
        receipt_submission=receipt_submission_service,
    )
