from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.customer_identity import (
    CustomerIdentityRepository,
    CustomerIdentitySubmission,
    SubmitCustomerIdentityCommand,
)


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class CustomerIdentityPersistenceError(RuntimeError):
    """Raised when the identity boundary receives an invalid RPC response."""


class SupabaseCustomerIdentityRepository(CustomerIdentityRepository):
    def __init__(self, client: SupabaseRpcClient) -> None:
        self._client = client

    async def submit(self, command: SubmitCustomerIdentityCommand) -> UUID:
        rows = await self._rpc(
            "submit_customer_identity",
            {
                "p_telegram_user_id": command.telegram_user_id,
                "p_full_name": command.full_name.strip(),
                "p_shamcash_account": command.shamcash_account.strip(),
                "p_telegram_contact_phone": command.telegram_contact_phone.strip(),
                "p_qr_image_file_id": command.qr_image_file_id.strip(),
            },
        )
        if len(rows) != 1 or str(rows[0].get("status")) != "PENDING":
            raise CustomerIdentityPersistenceError("identity submission returned invalid data")
        try:
            return UUID(str(rows[0]["submission_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise CustomerIdentityPersistenceError("identity submission id is invalid") from exc

    async def get_status(self, telegram_user_id: int) -> str | None:
        try:
            # First check if user is already verified
            user_res = await asyncio.to_thread(
                self._client.table("users")
                .select("verified_name, payment_identity_verified_at")
                .eq("telegram_user_id", telegram_user_id)
                .execute
            )
            data = getattr(user_res, "data", [])
            if data and data[0].get("payment_identity_verified_at"):
                return "APPROVED"

            # Check if user has a pending or recent submission
            user_id_row = data[0] if data else None
            # If user row exists, query customer_identity_submissions by user_id
            sub_res = await asyncio.to_thread(
                self._client.table("customer_identity_submissions")
                .select("status")
                .order("submitted_at", desc=True)
                .limit(1)
                .execute
            )
            # Alternatively query via RPC or filter
            rows = await self._rpc(
                "get_customer_payment_identity",
                {"p_telegram_user_id": telegram_user_id},
            )
            if rows:
                return "APPROVED"
            return None
        except Exception:
            return None

    async def list_pending(
        self, admin_telegram_user_id: int, actor_type: str
    ) -> tuple[CustomerIdentitySubmission, ...]:
        rows = await self._rpc(
            "list_pending_customer_identity_submissions",
            {"p_admin_telegram_user_id": admin_telegram_user_id, "p_actor_type": actor_type},
        )
        return tuple(self._submission(row) for row in rows)

    async def approve(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID
    ) -> None:
        await self._mutation(
            "approve_customer_identity_submission",
            {
                "p_admin_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_submission_id": str(submission_id),
            },
        )

    async def reject(
        self, admin_telegram_user_id: int, actor_type: str, submission_id: UUID, reason: str
    ) -> None:
        await self._mutation(
            "reject_customer_identity_submission",
            {
                "p_admin_telegram_user_id": admin_telegram_user_id,
                "p_actor_type": actor_type,
                "p_submission_id": str(submission_id),
                "p_rejection_reason": reason,
            },
        )

    async def _mutation(self, name: str, params: dict[str, Any]) -> None:
        rows = await self._rpc(name, params)
        if len(rows) != 1 or not isinstance(next(iter(rows[0].values()), None), bool) or not next(iter(rows[0].values())):
            raise CustomerIdentityPersistenceError("identity review returned invalid data")

    async def _rpc(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = await asyncio.to_thread(self._client.rpc(name, params).execute)
        except Exception as exc:
            raise CustomerIdentityPersistenceError("customer identity RPC failed") from exc
        if getattr(response, "error", None):
            raise CustomerIdentityPersistenceError("customer identity RPC returned an error")
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise CustomerIdentityPersistenceError("customer identity RPC returned invalid data")
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _submission(row: dict[str, Any]) -> CustomerIdentitySubmission:
        try:
            submitted_at = datetime.fromisoformat(str(row["submitted_at"]).replace("Z", "+00:00"))
            if submitted_at.tzinfo is None:
                raise ValueError("timestamp must include timezone")
            return CustomerIdentitySubmission(
                submission_id=UUID(str(row["submission_id"])),
                customer_telegram_user_id=int(row["customer_telegram_user_id"]),
                full_name=str(row["full_name"]),
                shamcash_account=str(row["shamcash_account"]),
                qr_image_file_id=str(row["qr_image_file_id"]),
                submitted_at=submitted_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CustomerIdentityPersistenceError("identity queue data is invalid") from exc