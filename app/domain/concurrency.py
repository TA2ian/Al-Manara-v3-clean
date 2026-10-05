from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StaleVersionError(Exception):
    expected_version: int
    current_version: int

    def __str__(self) -> str:
        return (
            f"stale aggregate version: expected={self.expected_version}, "
            f"current={self.current_version}"
        )
