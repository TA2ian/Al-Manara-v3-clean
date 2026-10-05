from __future__ import annotations

from typing import Any

from app.application.admin_receipt_settings import (
    AdminReceiptSettingsRepository,
    AdminReceiptSettingsView,
)


import asyncio
import logging

LOGGER = logging.getLogger(__name__)


class SupabaseAdminReceiptSettingsRepository(AdminReceiptSettingsRepository):
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_settings(self, admin_telegram_user_id: int) -> AdminReceiptSettingsView:
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("settings")
                .select("receipt_submission_deadline_minutes")
                .eq("id", "true")
                .maybe_single()
                .execute()
            )
            data = res.data or {}
            deadline = data.get("receipt_submission_deadline_minutes", 60)
            return AdminReceiptSettingsView(deadline_minutes=int(deadline))
        except Exception as exc:
            LOGGER.warning("Could not fetch receipt_submission_deadline_minutes from DB, defaulting to 60: %s", exc)
            return AdminReceiptSettingsView(deadline_minutes=60)

    async def update_settings(self, admin_telegram_user_id: int, deadline_minutes: int) -> bool:
        try:
            res = await asyncio.to_thread(
                lambda: self._client.table("settings")
                .update({"receipt_submission_deadline_minutes": deadline_minutes})
                .eq("id", "true")
                .execute()
            )
            return bool(res.data)
        except Exception as exc:
            LOGGER.error("Failed to update receipt_submission_deadline_minutes: %s", exc)
            return False
