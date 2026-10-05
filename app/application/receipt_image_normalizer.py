from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from app.application.receipt_image_policy import ReceiptImagePolicy


@dataclass(frozen=True, slots=True)
class NormalizedReceiptImage:
    content: bytes
    mime_type: str
    width: int
    height: int


class ReceiptImageNormalizer:
    def __init__(self, policy: ReceiptImagePolicy | None = None) -> None:
        self._policy = policy or ReceiptImagePolicy()

    def normalize(self, content: bytes, mime_type: str) -> NormalizedReceiptImage:
        if not content:
            raise ValueError("receipt image is empty")
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("unsupported receipt image type")
        if len(content) > self._policy.max_upload_bytes:
            raise ValueError("receipt image exceeds the upload limit")

        try:
            with Image.open(BytesIO(content)) as source:
                self._policy.validate_dimensions(*source.size)
                image = ImageOps.exif_transpose(source)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")

                if max(image.size) > self._policy.working_longest_side_px:
                    scale = self._policy.working_longest_side_px / max(image.size)
                    target = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                    image = image.resize(target, Image.Resampling.LANCZOS)

                output = BytesIO()
                if mime_type == "image/png":
                    image.save(output, format="PNG", optimize=True)
                    output_mime = "image/png"
                else:
                    image.save(
                        output,
                        format="JPEG",
                        quality=self._policy.initial_jpeg_quality,
                        optimize=True,
                        progressive=True,
                    )
                    output_mime = "image/jpeg"

                return NormalizedReceiptImage(
                    content=output.getvalue(),
                    mime_type=output_mime,
                    width=image.width,
                    height=image.height,
                )
        except (OSError, ValueError) as exc:
            raise ValueError("receipt image normalization failed") from exc
