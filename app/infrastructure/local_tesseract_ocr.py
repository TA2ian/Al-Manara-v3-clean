import asyncio
import os
import tempfile
import uuid
import re
from decimal import Decimal

from app.domain.receipt_ocr import OcrField, OcrFieldValue, OcrResult, OcrPort

class LocalTesseractOcrAdapter(OcrPort):
    def __init__(self, tesseract_cmd: str = "tesseract") -> None:
        self._cmd = tesseract_cmd

    async def extract(self, image: bytes, mime_type: str, receipt_id: uuid.UUID) -> OcrResult:
        if not image:
            return OcrResult(receipt_id=receipt_id, fields={}, provider="tesseract", provider_version="local")
            
        fd, path = tempfile.mkstemp(suffix=".img")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(image)
            
            # Using shell=False and safe list arguments
            process = await asyncio.create_subprocess_exec(
                self._cmd,
                path,
                "stdout",
                "-l", "ara+eng",
                "quiet",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15.0)
            
            if process.returncode != 0:
                return OcrResult(
                    receipt_id=receipt_id,
                    fields={},
                    provider="tesseract",
                    provider_version="local",
                )
                
            text = stdout.decode("utf-8", errors="ignore")
            fields = self._parse_text(text)
            
            return OcrResult(
                receipt_id=receipt_id,
                fields=fields,
                provider="tesseract",
                provider_version="local",
            )
        except Exception:
            return OcrResult(
                receipt_id=receipt_id,
                fields={},
                provider="tesseract",
                provider_version="local",
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _parse_text(self, text: str) -> dict[OcrField, OcrFieldValue]:
        fields = {}
        text_upper = text.upper()
        
        # Public Order Code: ORD-XXXXXXXXXX
        match = re.search(r'ORD-[A-Z0-9]{10}', text_upper)
        if match:
            fields[OcrField.REFERENCE] = OcrFieldValue(value=match.group(0), confidence=Decimal("0.85"))
            
        # Currency Detection (ShamCash supports USD / NEW.SYP)
        if "USD" in text_upper:
            fields[OcrField.CURRENCY] = OcrFieldValue(value="USD", confidence=Decimal("0.85"))
        elif "SYP" in text_upper or "ل.س" in text_upper or "ليرة" in text_upper:
            fields[OcrField.CURRENCY] = OcrFieldValue(value="NEW.SYP", confidence=Decimal("0.85"))
            
        # Amount Extraction: Look for numbers with dots or commas
        # This relies on the receipt_ocr_normalizer in the app layer for exact cleanup.
        amount_matches = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?\b', text_upper)
        if amount_matches:
            best_match = amount_matches[0]
            fields[OcrField.AMOUNT] = OcrFieldValue(value=best_match, confidence=Decimal("0.75"))
            
        return fields
