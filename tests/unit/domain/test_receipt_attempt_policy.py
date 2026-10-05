import pytest

from app.domain.receipt_attempt_policy import ReceiptAttemptOutcome, resolve_attempt


def test_first_failed_attempt_allows_retry() -> None:
    result = resolve_attempt(attempt_number=1, max_attempts=3, verified=False, reason="amount_mismatch")
    assert result.outcome is ReceiptAttemptOutcome.FAILED
    assert result.reason == "amount_mismatch"


def test_second_failed_attempt_allows_final_retry() -> None:
    result = resolve_attempt(attempt_number=2, max_attempts=3, verified=False)
    assert result.outcome is ReceiptAttemptOutcome.FAILED


def test_third_failed_attempt_escalates() -> None:
    result = resolve_attempt(attempt_number=3, max_attempts=3, verified=False)
    assert result.outcome is ReceiptAttemptOutcome.ESCALATED


def test_success_never_escalates() -> None:
    result = resolve_attempt(attempt_number=3, max_attempts=3, verified=True)
    assert result.outcome is ReceiptAttemptOutcome.VERIFIED


def test_invalid_attempt_number_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_attempt(attempt_number=4, max_attempts=3, verified=False)
