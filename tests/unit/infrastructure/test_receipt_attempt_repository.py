from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.receipt_attempt import ReceiptAttemptStatus
from app.infrastructure.persistence.receipt_attempt_repository import (
    ReceiptPersistenceConflictError,
    ReceiptPersistenceError,
    ReceiptPersistenceNotFoundError,
    SupabaseReceiptAttemptRepository,
)


@dataclass
class FakeResponse:
    data: list[dict] | None = None
    error: object | None = None


class FakeQuery:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.execute_calls = 0

    def execute(self) -> FakeResponse:
        self.execute_calls += 1
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.function_name: str | None = None
        self.params: dict | None = None
        self.query = FakeQuery(response)

    def rpc(self, function_name: str, params: dict) -> FakeQuery:
        self.function_name = function_name
        self.params = params
        return self.query


@pytest.mark.asyncio
async def test_reserve_maps_rpc_payload_and_preserves_identity_and_idempotency_key() -> None:
    order_id = uuid4()
    submission_id = uuid4()
    telegram_user_id = 7001
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(
        FakeResponse(
            data=[
                {
                    "submission_id": str(submission_id),
                    "internal_order_id": str(order_id),
                    "attempt_number": 1,
                    "telegram_file_id": "file-1",
                    "mime_type": "image/png",
                    "submitted_at": submitted_at.isoformat(),
                    "processing_status": "PROCESSING",
                    "replayed": False,
                }
            ]
        )
    )
    repository = SupabaseReceiptAttemptRepository(client)

    reservation = await repository.reserve_next_attempt(
        order_id=order_id,
        telegram_user_id=telegram_user_id,
        idempotency_key=" update-123 ",
        submitted_at=submitted_at,
        mime_type="image/png",
        telegram_file_id=" file-1 ",
    )

    assert client.function_name == "reserve_receipt_submission"
    assert client.params == {
        "p_order_id": str(order_id),
        "p_telegram_user_id": telegram_user_id,
        "p_idempotency_key": "update-123",
        "p_telegram_file_id": "file-1",
        "p_mime_type": "image/png",
        "p_submitted_at": submitted_at.isoformat(),
    }
    assert reservation.replayed is False
    assert reservation.attempt.attempt_id == submission_id
    assert reservation.attempt.order_id == order_id
    assert reservation.attempt.status is ReceiptAttemptStatus.PROCESSING
    assert client.query.execute_calls == 1


@pytest.mark.asyncio
async def test_replayed_reservation_is_mapped_without_processing_side_effects() -> None:
    order_id = uuid4()
    submission_id = uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(
        FakeResponse(
            data=[
                {
                    "submission_id": str(submission_id),
                    "internal_order_id": str(order_id),
                    "attempt_number": 2,
                    "telegram_file_id": "file-2",
                    "mime_type": "image/jpeg",
                    "submitted_at": submitted_at.isoformat(),
                    "processing_status": "FAILED",
                    "failure_reason": "previous OCR failure",
                    "replayed": True,
                }
            ]
        )
    )
    repository = SupabaseReceiptAttemptRepository(client)

    reservation = await repository.reserve_next_attempt(
        order_id,
        7001,
        "update-123",
        submitted_at,
        "image/jpeg",
        "file-2",
    )

    assert reservation.replayed is True
    assert reservation.attempt.status is ReceiptAttemptStatus.FAILED
    assert reservation.attempt.failure_reason == "previous OCR failure"


@pytest.mark.asyncio
async def test_finalize_maps_succeeded_payload() -> None:
    order_id = uuid4()
    submission_id = uuid4()
    submitted_at = datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)
    client = FakeClient(
        FakeResponse(
            data=[
                {
                    "submission_id": str(submission_id),
                    "internal_order_id": str(order_id),
                    "attempt_number": 1,
                    "telegram_file_id": "file-1",
                    "mime_type": "image/webp",
                    "submitted_at": submitted_at.isoformat(),
                    "processing_status": "SUCCEEDED",
                    "linkage_status": "LINKED",
                    "failure_reason": None,
                }
            ]
        )
    )
    repository = SupabaseReceiptAttemptRepository(client)

    result = await repository.finalize(submission_id, ReceiptAttemptStatus.VERIFIED)

    assert client.function_name == "finalize_receipt_submission"
    assert client.params == {
        "p_submission_id": str(submission_id),
        "p_processing_status": "SUCCEEDED",
        "p_failure_reason": None,
    }
    assert result.status is ReceiptAttemptStatus.VERIFIED
    assert result.mime_type == "image/webp"
    assert result.telegram_file_id == "file-1"


@pytest.mark.asyncio
async def test_finalize_rejects_processing_status() -> None:
    repository = SupabaseReceiptAttemptRepository(FakeClient(FakeResponse(data=[])))

    with pytest.raises(ValueError, match="PROCESSING cannot be finalized"):
        await repository.finalize(uuid4(), ReceiptAttemptStatus.PROCESSING)


@pytest.mark.asyncio
async def test_empty_rpc_result_is_not_silently_accepted() -> None:
    repository = SupabaseReceiptAttemptRepository(FakeClient(FakeResponse(data=[])))

    with pytest.raises(ReceiptPersistenceNotFoundError, match="returned no row"):
        await repository.finalize(uuid4(), ReceiptAttemptStatus.VERIFIED)


@pytest.mark.asyncio
async def test_database_conflict_is_mapped_to_conflict_error() -> None:
    client = FakeClient(
        FakeResponse(error={"message": "receipt attempt limit reached"})
    )
    repository = SupabaseReceiptAttemptRepository(client)

    with pytest.raises(ReceiptPersistenceConflictError, match="attempt limit"):
        await repository.reserve_next_attempt(
            uuid4(),
            7001,
            "update-123",
            datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc),
            "image/png",
            "file-1",
        )


@pytest.mark.asyncio
async def test_unknown_database_error_is_wrapped() -> None:
    client = FakeClient(FakeResponse(error={"message": "permission denied"}))
    repository = SupabaseReceiptAttemptRepository(client)

    with pytest.raises(ReceiptPersistenceError, match="permission denied"):
        await repository.reserve_next_attempt(
            uuid4(),
            7001,
            "update-123",
            datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc),
            "image/png",
            "file-1",
        )


@pytest.mark.asyncio
async def test_order_ownership_conflict_is_mapped_to_conflict_error() -> None:
    client = FakeClient(
        FakeResponse(error={"message": "order does not belong to telegram user"})
    )
    repository = SupabaseReceiptAttemptRepository(client)

    with pytest.raises(ReceiptPersistenceConflictError, match="does not belong"):
        await repository.reserve_next_attempt(
            uuid4(),
            7001,
            "update-123",
            datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc),
            "image/png",
            "file-1",
        )
