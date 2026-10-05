from __future__ import annotations

import re

_REFERENCE_RE = re.compile(r"[^A-Z0-9]")


def normalize_reference(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = _REFERENCE_RE.sub("", raw.strip().upper())
    return normalized or None


def references_match(expected: str | None, extracted: str | None) -> bool | None:
    normalized_expected = normalize_reference(expected)
    normalized_extracted = normalize_reference(extracted)
    if normalized_expected is None or normalized_extracted is None:
        return None
    return normalized_expected == normalized_extracted
