"""All customer-facing and admin-facing message strings in one place.

Now powered by dynamic i18n localization via PEP 562 module-level __getattr__.
"""
from __future__ import annotations

from typing import Any

from app.runtime.telegram.shared.i18n import get_text


def safe(message: object | None, fallback: str) -> str:
    """Return non-empty string message or the provided fallback."""
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


def __getattr__(name: str) -> Any:
    """Dynamically resolve message keys using i18n."""
    if name == "safe":
        return safe
    # If a module attempts to import a constant like ADMIN_PRIVATE_ONLY,
    # this will return the translated string based on the current contextvar.
    # Note: If imported as `from ...messages import XYZ`, it evaluates once.
    # We rely on handlers using `messages.XYZ` to ensure dynamic evaluation.
    return get_text(name)
