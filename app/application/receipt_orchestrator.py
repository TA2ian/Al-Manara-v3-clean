from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.receipt_image import ReceiptImageInspectorImpl
from app.application.receipt_image_normalizer import ReceiptImageNormalizer
from app.application.receipt_ocr_normalizer import normalize_amount, normalize_currency_field
from app.application.receipt_verification_service import ReceiptFinancialVerificationService, ReceiptVerificationInput
from app.domain.receipt_attempt import ReceiptAttemptStatus
from app.domain.receipt_ocr import OcrField, OcrPort
from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision


@dataclass(frozen=True, slots=True)
class ReceiptSubmission:
    order_id: UUID
    attempt_id: UUID
    telegram_file_id: str
    mime_type: str


class ReceiptAttemptFinalizer:
    async def finalize(self, attempt_id: UUID, status: ReceiptAttemptStatus, reason: str | None = None):
        raise NotImplementedError


class ReceiptSubmissionOrchestrator:
    def __init__(self, inspector: ReceiptImageInspectorImpl, normalizer: ReceiptImageNormalizer, ocr: OcrPort, verification: ReceiptFinancialVerificationService, finalizer: ReceiptAttemptFinalizer) -> None:
        self._inspector = inspector
        self._normalizer = normalizer
        self._ocr = ocr
        self._verification = verification
        self._finalizer = finalizer

    async def process(self, submission: ReceiptSubmission, image_bytes: bytes):
        finalized = False
        try:
            inspected = await self._inspector.inspect_bytes(image_bytes, submission.mime_type)
            normalized = self._normalizer.normalize(inspected.content, inspected.mime_type)
            ocr_result = await self._ocr.extract(normalized.content, normalized.mime_type, submission.attempt_id)
            fields = ocr_result.fields

            raw_amount = fields[OcrField.AMOUNT].value if OcrField.AMOUNT in fields else None
            raw_currency = fields[OcrField.CURRENCY].value if OcrField.CURRENCY in fields else None
            amount = normalize_amount(raw_amount) if raw_amount else None
            currency = normalize_currency_field(raw_currency)
            extracted = ExtractedReceiptData(
                receipt_id=submission.attempt_id,
                amount=amount,
                currency=currency.value if currency is not None else None,
                reference=fields[OcrField.REFERENCE].value if OcrField.REFERENCE in fields else None,
                network=fields[OcrField.NETWORK].value if OcrField.NETWORK in fields else None,
                confidence=min((field.confidence for field in fields.values()), default=0),
            )
            verification = await self._verification.verify(ReceiptVerificationInput(submission.order_id, extracted))
            decision = verification.evidence.decision

            if decision is VerificationDecision.VERIFIED:
                finalized = True
                return await self._finalizer.finalize(submission.attempt_id, ReceiptAttemptStatus.VERIFIED)

            reason = ";".join(verification.evidence.reasons) or decision.value
            status = ReceiptAttemptStatus.ESCALATED if decision is VerificationDecision.SUSPICIOUS and submission.attempt_id is not None and await self._is_third_attempt(submission.attempt_id) else ReceiptAttemptStatus.FAILED
            finalized = True
            return await self._finalizer.finalize(submission.attempt_id, status, reason)
        except Exception as exc:
            if not finalized:
                reason = str(exc).strip() or "receipt processing failed"
                await self._finalizer.finalize(submission.attempt_id, ReceiptAttemptStatus.FAILED, reason)
            raise

    async def _is_third_attempt(self, attempt_id: UUID) -> bool:
        checker = getattr(self._finalizer, "is_third_attempt", None)
        if checker is None:
            return False
        return bool(await checker(attempt_id))
