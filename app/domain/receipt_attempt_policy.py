from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReceiptAttemptOutcome(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass(frozen=True, slots=True)
class ReceiptAttemptResolution:
    outcome: ReceiptAttemptOutcome
    reason: str | None


def resolve_attempt(*, attempt_number: int, max_attempts: int, verified: bool, reason: str | None = None) -> ReceiptAttemptResolution:
    if attempt_number < 1:
        raise ValueError("attempt_number must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    if attempt_number > max_attempts:
        raise ValueError("attempt_number exceeds max_attempts")
    if verified:
        return ReceiptAttemptResolution(ReceiptAttemptOutcome.VERIFIED, None)
    if attempt_number == max_attempts:
        return ReceiptAttemptResolution(ReceiptAttemptOutcome.ESCALATED, reason or "maximum receipt attempts exhausted")
    return ReceiptAttemptResolution(ReceiptAttemptOutcome.FAILED, reason or "receipt verification failed")
