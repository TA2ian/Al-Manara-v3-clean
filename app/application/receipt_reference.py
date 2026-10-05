from __future__ import annotations

import re

_REFERENCE_ALLOWED = re.compile(r"[^A-Z0-9]")


def normalize_reference(raw: str) -> str | None:
    normalized = _REFERENCE_ALLOWED.sub("", raw.strip().upper())
    return normalized or None


def references_match(expected: str | None, extracted: str | None) -> bool | None:
    expected_normalized = normalize_reference(expected) if expected else None
    extracted_normalized = normalize_reference(extracted) if extracted else None
    if not expected_normalized or not extracted_normalized:
        return None
    return expected_normalized == extracted_normalized
