from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.infrastructure.persistence.admin_super_tools_repository import SupabaseAdminSuperToolsRepository
from app.infrastructure.persistence.user_repository import SupabaseUserRepository


class SuperAdminService:
    def __init__(
        self,
        super_tools_repo: SupabaseAdminSuperToolsRepository,
        user_repo: SupabaseUserRepository,
        authorization_repo: Any,
    ) -> None:
        self._super_tools = super_tools_repo
        self._user_repo = user_repo
        self._auth = authorization_repo

    async def reset_order(
        self,
        admin_user_id: int,
        order_id_or_code: str | UUID,
        target_status: str = "UNDER_REVIEW",
    ) -> bool:
        order_id = await self._resolve_order_id(order_id_or_code)
        if not order_id:
            return False
        return await self._super_tools.reset_order_status(
            admin_user_id=admin_user_id,
            internal_order_id=order_id,
            target_status=target_status,
        )

    async def edit_order(
        self,
        admin_user_id: int,
        order_id_or_code: str | UUID,
        new_amount: Decimal | None = None,
        new_currency: str | None = None,
        new_network: str | None = None,
    ) -> bool:
        order_id = await self._resolve_order_id(order_id_or_code)
        if not order_id:
            return False
        return await self._super_tools.edit_order_details(
            admin_user_id=admin_user_id,
            internal_order_id=order_id,
            new_amount=new_amount,
            new_currency=new_currency,
            new_network=new_network,
        )

    async def delete_order(
        self,
        admin_user_id: int,
        order_id_or_code: str | UUID,
    ) -> bool:
        order_id = await self._resolve_order_id(order_id_or_code)
        if not order_id:
            return False
        return await self._super_tools.delete_order(
            admin_user_id=admin_user_id,
            internal_order_id=order_id,
        )

    async def unsuspend_user(
        self,
        admin_user_id: int,
        target_telegram_id: int,
    ) -> bool:
        return await self._user_repo.unsuspend_user(
            admin_user_id=admin_user_id,
            target_telegram_id=target_telegram_id,
        )

    async def force_verify_user(
        self,
        admin_user_id: int,
        target_telegram_id: int,
    ) -> bool:
        return await self._user_repo.force_verify_user(
            admin_user_id=admin_user_id,
            target_telegram_id=target_telegram_id,
        )

    async def bypass_ocr_and_approve(
        self,
        admin_user_id: int,
        order_id_or_code: str | UUID,
    ) -> bool:
        order_id = await self._resolve_order_id(order_id_or_code)
        if not order_id:
            return False
        return await self._super_tools.reset_order_status(
            admin_user_id=admin_user_id,
            internal_order_id=order_id,
            target_status="APPROVED",
            reason="Bypassed by admin for testing",
        )

    async def _resolve_order_id(self, order_id_or_code: str | UUID) -> UUID | None:
        if isinstance(order_id_or_code, UUID):
            return order_id_or_code
        try:
            return UUID(order_id_or_code)
        except ValueError:
            return await self._super_tools.get_order_id_by_code(order_id_or_code)
