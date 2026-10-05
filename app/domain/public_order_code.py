from __future__ import annotations

import secrets
import string


_ALPHABET = string.ascii_uppercase + string.digits
_PREFIX = "ORD-"
_LENGTH = 10


def generate_public_order_code() -> str:
    """Generate an opaque, non-sequential customer-facing order code."""
    value = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
    return f"{_PREFIX}{value}"
