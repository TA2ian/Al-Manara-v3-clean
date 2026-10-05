from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiptImagePolicy:
    max_upload_bytes: int = 4 * 1024 * 1024
    max_longest_side_px: int = 6000
    max_pixels: int = 20_000_000
    min_shortest_side_px: int = 500
    working_longest_side_px: int = 3000
    initial_jpeg_quality: int = 85
    minimum_jpeg_quality: int = 65

    def __post_init__(self) -> None:
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        if self.max_longest_side_px <= 0 or self.max_pixels <= 0:
            raise ValueError("image dimension limits must be positive")
        if self.min_shortest_side_px <= 0:
            raise ValueError("min_shortest_side_px must be positive")
        if self.working_longest_side_px <= 0:
            raise ValueError("working_longest_side_px must be positive")
        if not 1 <= self.minimum_jpeg_quality <= self.initial_jpeg_quality <= 100:
            raise ValueError("invalid jpeg quality bounds")

    def validate_dimensions(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("image dimensions must be positive")
        if max(width, height) > self.max_longest_side_px:
            raise ValueError("image exceeds the maximum dimension")
        if width * height > self.max_pixels:
            raise ValueError("image exceeds the maximum pixel count")
        if min(width, height) < self.min_shortest_side_px:
            raise ValueError("image is too small to reliably read receipt data")
