from __future__ import annotations

from decimal import Decimal

from app.domain.receipt_evidence import EvidenceMatch, VerificationEvidence
from app.domain.receipt_verification import ExtractedReceiptData, VerificationDecision
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_engine import VerificationEngineResult
from app.domain.receipt_reference import references_match
from app.domain.network import normalize_network


def build_verification_evidence(
    context: ReceiptVerificationContext,
    extracted: ExtractedReceiptData,
    result: VerificationEngineResult,
) -> VerificationEvidence:
    if extracted.amount is None:
        amount = EvidenceMatch.UNAVAILABLE
    elif result.financial_match is not None and result.financial_match.decision is VerificationDecision.VERIFIED:
        amount = EvidenceMatch.MATCHED
    else:
        amount = EvidenceMatch.MISMATCHED

    if extracted.currency is None:
        currency = EvidenceMatch.UNAVAILABLE
    elif extracted.currency == context.payment_currency.value:
        currency = EvidenceMatch.MATCHED
    else:
        currency = EvidenceMatch.MISMATCHED

    if extracted.network is None:
        network = EvidenceMatch.UNAVAILABLE
    else:
        normalized = normalize_network(extracted.network)
        network = EvidenceMatch.MATCHED if normalized is not None and normalized.value == context.network_code else EvidenceMatch.MISMATCHED

    reference = EvidenceMatch.UNAVAILABLE
    if context.expected_reference:
        reference_match = references_match(context.expected_reference, extracted.reference)
        reference = EvidenceMatch.MATCHED if reference_match is True else EvidenceMatch.MISMATCHED if reference_match is False else EvidenceMatch.UNAVAILABLE
    elif extracted.reference:
        reference = EvidenceMatch.NOT_CHECKED

    return VerificationEvidence(
        amount=amount,
        currency=currency,
        network=network,
        reference=reference,
        ocr_confidence=extracted.confidence,
        tolerance_used=context.tolerance,
        reasons=result.reasons,
        decision=result.decision,
    )
