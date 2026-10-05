from __future__ import annotations

from dataclasses import dataclass

from app.domain.currency import normalize_currency
from app.domain.network import normalize_network
from app.domain.receipt_reference import references_match
from app.domain.receipt_verification import ExtractedReceiptData, FinancialMatchResult, VerificationDecision, match_receipt_amount
from app.domain.receipt_verification_context import ReceiptVerificationContext
from app.domain.receipt_verification_policy import DEFAULT_RECEIPT_VERIFICATION_POLICY, ReceiptVerificationPolicy


@dataclass(frozen=True, slots=True)
class VerificationEngineResult:
    decision: VerificationDecision
    financial_match: FinancialMatchResult | None
    reasons: tuple[str, ...]


def verify_receipt(
    context: ReceiptVerificationContext,
    extracted: ExtractedReceiptData,
    policy: ReceiptVerificationPolicy = DEFAULT_RECEIPT_VERIFICATION_POLICY,
) -> VerificationEngineResult:
    reasons: list[str] = []

    if extracted.confidence < policy.minimum_ocr_confidence:
        reasons.append("ocr_confidence_below_threshold")

    if extracted.currency is None or extracted.amount is None:
        return VerificationEngineResult(VerificationDecision.INSUFFICIENT_DATA, None, tuple(reasons + ["missing_amount_or_currency"]))

    normalized_extracted_currency = normalize_currency(extracted.currency)
    if normalized_extracted_currency is None:
        return VerificationEngineResult(VerificationDecision.SUSPICIOUS, None, tuple(reasons + ["unknown_currency"]))

    if normalized_extracted_currency is not context.payment_currency:
        return VerificationEngineResult(VerificationDecision.MISMATCH, None, tuple(reasons + ["currency_mismatch"]))

    financial = match_receipt_amount(context.expected_payment_amount, extracted, context.tolerance)
    if financial.decision is VerificationDecision.MISMATCH:
        return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["amount_mismatch"]))

    if extracted.network is None:
        if policy.require_network and policy.allow_missing_network_as_suspicious:
            return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons + ["network_required_but_unavailable"]))
        if policy.require_network:
            return VerificationEngineResult(VerificationDecision.INSUFFICIENT_DATA, financial, tuple(reasons + ["network_required_but_unavailable"]))
    else:
        normalized_network = normalize_network(extracted.network)
        if normalized_network is None:
            return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons + ["unknown_network"]))
        if normalized_network.value != context.network_code:
            return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["network_mismatch"]))

    if policy.require_reference or context.expected_reference is not None:
        reference_result = references_match(context.expected_reference, extracted.reference)
        if reference_result is False:
            return VerificationEngineResult(VerificationDecision.MISMATCH, financial, tuple(reasons + ["reference_mismatch"]))
        if reference_result is None:
            return VerificationEngineResult(VerificationDecision.INSUFFICIENT_DATA, financial, tuple(reasons + ["reference_required_but_unavailable"]))
    elif extracted.reference is None:
        reasons.append("reference_not_available")

    if extracted.confidence < policy.minimum_ocr_confidence:
        return VerificationEngineResult(VerificationDecision.SUSPICIOUS, financial, tuple(reasons))

    return VerificationEngineResult(VerificationDecision.VERIFIED, financial, tuple(reasons))
