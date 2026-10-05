from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptReservation
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus


class SupabaseRpcQuery(Protocol):
    def execute(self) -> Any: ...


class SupabaseRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> SupabaseRpcQuery: ...


class ReceiptPersistenceError(RuntimeError):
    """Base error raised when the persistence boundary cannot complete an operation."""


class ReceiptPersistenceConflictError(ReceiptPersistenceError):
    """Raised when PostgreSQL rejects an operation because of a state conflict."""


class ReceiptPersistenceNotFoundError(ReceiptPersistenceError):
    """Raised when PostgreSQL cannot find the requested receipt submission."""


_PROCESSING_STATUS_MAP: dict[str, ReceiptAttemptStatus] = {
    "PROCESSING": ReceiptAttemptStatus.PROCESSING,
    "SUCCEEDED": ReceiptAttemptStatus.VERIFIED,
    "FAILED": ReceiptAttemptStatus.FAILED,
    "ESCALATED": ReceiptAttemptStatus.ESCALATED,
}


@dataclass(frozen=True, slots=True)
class SupabaseReceiptAttemptRepository(ReceiptAttemptRepository):
    client: SupabaseRpcClient

    async def reserve_next_attempt(
        self,
        order_id: UUID,
        telegram_user_id: int,
        idempotency_key: str,
        submitted_at: datetime,
        mime_type: str,
        telegram_file_id: str,
    ) -> ReceiptReservation:
        params = {
            "p_order_id": str(order_id),
            "p_telegram_user_id": telegram_user_id,
            "p_idempotency_key": idempotency_key.strip(),
            "p_telegram_file_id": telegram_file_id.strip(),
            "p_mime_type": mime_type,
            "p_submitted_at": submitted_at.isoformat(),
        }
        rows = await self._rpc("reserve_receipt_submission", params)
        row = self._single_row(rows, "reserve_receipt_submission")
        return ReceiptReservation(
            attempt=self._map_attempt(row),
            replayed=self._map_bool(row, "replayed"),
        )

    async def finalize(
        self,
        attempt_id: UUID,
        status: ReceiptAttemptStatus,
        failure_reason: str | None = None,
    ) -> ReceiptAttempt:
        processing_status = self._to_processing_status(status)
        params = {
            "p_submission_id": str(attempt_id),
            "p_processing_status": processing_status,
            "p_failure_reason": failure_reason.strip() if failure_reason is not None else None,
        }
        rows = await self._rpc("finalize_receipt_submission", params)
        row = self._single_row(rows, "finalize_receipt_submission")
        return self._map_attempt(row, expected_status=status)

    async def _rpc(self, function_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            query = self.client.rpc(function_name, params)
            response = await asyncio.to_thread(query.execute)
        except Exception as exc:
            raise ReceiptPersistenceError(
                f"receipt persistence RPC failed: {function_name}"
            ) from exc

        error = getattr(response, "error", None)
        if error:
            message = self._error_message(error)
            self._raise_mapped_error(function_name, message)

        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise ReceiptPersistenceError(
                f"receipt persistence RPC returned invalid data: {function_name}"
            )
        return [dict(row) for row in data if isinstance(row, dict)]

    @staticmethod
    def _single_row(rows: list[dict[str, Any]], operation: str) -> dict[str, Any]:
        if not rows:
            raise ReceiptPersistenceNotFoundError(
                f"receipt persistence RPC returned no row: {operation}"
            )
        if len(rows) != 1:
            raise ReceiptPersistenceError(
                f"receipt persistence RPC returned {len(rows)} rows: {operation}"
            )
        return rows[0]

    @staticmethod
    def _map_attempt(
        row: dict[str, Any],
        expected_status: ReceiptAttemptStatus | None = None,
    ) -> ReceiptAttempt:
        try:
            raw_status = str(row["processing_status"]).strip().upper()
            try:
                status = _PROCESSING_STATUS_MAP[raw_status]
            except KeyError as exc:
                raise ReceiptPersistenceError(
                    f"unknown receipt processing status: {raw_status}"
                ) from exc
            if expected_status is not None and status is not expected_status:
                raise ReceiptPersistenceError(
                    "receipt finalization returned an unexpected processing status"
                )
            return ReceiptAttempt(
                attempt_id=UUID(str(row["submission_id"])),
                order_id=UUID(str(row["internal_order_id"])),
                attempt_number=int(row["attempt_number"]),
                mime_type=str(row["mime_type"]),
                telegram_file_id=str(row["telegram_file_id"]),
                submitted_at=SupabaseReceiptAttemptRepository._parse_datetime(row["submitted_at"]),
                status=status,
                failure_reason=(
                    str(row["failure_reason"])
                    if row.get("failure_reason") is not None
                    else None
                ),
            )
        except ReceiptPersistenceError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ReceiptPersistenceError("invalid receipt persistence payload") from exc

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("invalid receipt timestamp")
        if result.tzinfo is None:
            raise ValueError("receipt timestamp must be timezone-aware")
        return result

    @staticmethod
    def _map_bool(row: dict[str, Any], key: str) -> bool:
        value = row.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ReceiptPersistenceError(f"invalid boolean field: {key}")

    @staticmethod
    def _to_processing_status(status: ReceiptAttemptStatus) -> str:
        mapping = {
            ReceiptAttemptStatus.VERIFIED: "SUCCEEDED",
            ReceiptAttemptStatus.FAILED: "FAILED",
            ReceiptAttemptStatus.ESCALATED: "ESCALATED",
        }
        try:
            return mapping[status]
        except KeyError as exc:
            raise ValueError("PROCESSING cannot be finalized") from exc

    @staticmethod
    def _error_message(error: Any) -> str:
        if isinstance(error, str):
            return error.strip()
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        if isinstance(error, dict):
            value = error.get("message") or error.get("details") or error.get("hint")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(error).strip() or "unknown persistence error"

    @classmethod
    def _raise_mapped_error(cls, function_name: str, message: str) -> None:
        normalized = message.lower()
        if any(
            marker in normalized
            for marker in (
                "order does not belong to telegram user",
                "user is disabled",
                "order does not accept receipts",
                "receipt is already being processed",
                "receipt attempt limit reached",
                "idempotency key belongs to another order",
                "receipt submission is not processing",
                "only the third receipt attempt may escalate",
            )
        ):
            raise ReceiptPersistenceConflictError(
                f"{function_name} rejected the receipt operation: {message}"
            )
        if any(marker in normalized for marker in ("order not found", "receipt submission not found", "telegram user not found")):
            raise ReceiptPersistenceNotFoundError(
                f"{function_name} target was not found: {message}"
            )
        raise ReceiptPersistenceError(f"{function_name} failed: {message}")
