from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.receipt_evidence import VerificationEvidence
from app.domain.receipt_verification import ExtractedReceiptData
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_engine import verify_receipt
from app.application.receipt_verification_evidence import build_verification_evidence


@dataclass(frozen=True, slots=True)
class ReceiptVerificationInput:
    order_id: UUID
    extracted: ExtractedReceiptData


@dataclass(frozen=True, slots=True)
class ReceiptVerificationOutput:
    evidence: VerificationEvidence


class OrderVerificationSnapshotReader(Protocol):
    async def get_receipt_verification_context(self, order_id: UUID) -> ReceiptVerificationContext | None: ...


class ReceiptFinancialVerificationService:
    def __init__(self, snapshots: OrderVerificationSnapshotReader) -> None:
        self._snapshots = snapshots

    async def verify(self, request: ReceiptVerificationInput) -> ReceiptVerificationOutput:
        context = await self._snapshots.get_receipt_verification_context(request.order_id)
        if context is None:
            raise LookupError("order verification snapshot not found")
        result = verify_receipt(context, request.extracted)
        evidence = build_verification_evidence(context, request.extracted, result)
        return ReceiptVerificationOutput(evidence=evidence)
