"""Smart Arabic Rejection Template Generator for Admin Reviews."""
from __future__ import annotations

OCR_REASON_ARABIC_MAP: dict[str, str] = {
    "amount_mismatch": "عدم تطابق المبلغ المكتوب في الإيصال مع قيمة الطلب في النظام.",
    "currency_mismatch": "اختلاف عملة الدفع الموجودة في الإيصال عن العملة المحددة في الطلب.",
    "ocr_confidence_below_threshold": "انخفاض وضوح صورة الإيصال وتعذر قراءة البيانات الآلية تلقائياً.",
    "unknown_currency": "العملة الموجودة في الإيصال غير معروفة أو غير مدعومة.",
    "unknown_network": "الشبكة المحددة في الإيصال غير مطابقة لشبكة الدفع المطلوب.",
    "network_mismatch": "الشبكة الموجودة بالإيصال لا تطابق شبكة الطلب.",
    "reference_mismatch": "الرقم المرجعي (Reference/TXID) في الإيصال غير مطابق للبيانات.",
    "reference_required_but_unavailable": "الرقم المرجعي مفقود أو غير واضح في الإيصال المرفوع.",
    "missing_amount_or_currency": "المبلغ أو العملة غير ظاهرين بشكل واضح في صورة الإيصال.",
    "network_required_but_unavailable": "بيانات شبكة التحويل غير ظاهرة في الإيصال.",
}


def build_rejection_explanation(reasons: str | list[str] | tuple[str, ...]) -> str:
    """Generate a clean, structured Arabic explanation text based on OCR/system failure reasons."""
    if isinstance(reasons, str):
        reason_list = [r.strip() for r in reasons.replace(";", ",").split(",") if r.strip()]
    else:
        reason_list = [str(r).strip() for r in reasons if str(r).strip()]

    matched_explanations: list[str] = []
    for reason_code in reason_list:
        if reason_code in OCR_REASON_ARABIC_MAP:
            matched_explanations.append(f"• {OCR_REASON_ARABIC_MAP[reason_code]}")

    if not matched_explanations:
        return "تم رفض الإيصال لعدم استيفاء الشروط والبيانات المطلوبة للإشعار. يرجى التأكد من رفع إيصال صالح وواضح."

    body = "\n".join(matched_explanations)
    return (
        f"عذراً، تعذر قبول الإيصال المرفوع للأسباب التالية:\n"
        f"{body}\n\n"
        f"يرجى التأكد من رفع الإيصال الصحيح والواضح وإعادة المحاولة."
    )


def build_clarification_explanation(reasons: str | list[str] | tuple[str, ...]) -> str:
    """Generate a clean Arabic clarification request text."""
    if isinstance(reasons, str):
        reason_list = [r.strip() for r in reasons.replace(";", ",").split(",") if r.strip()]
    else:
        reason_list = [str(r).strip() for r in reasons if str(r).strip()]

    matched_explanations: list[str] = []
    for reason_code in reason_list:
        if reason_code in OCR_REASON_ARABIC_MAP:
            matched_explanations.append(f"• {OCR_REASON_ARABIC_MAP[reason_code]}")

    if not matched_explanations:
        return "يرجى تقديم صورة أوضح للإيصال أو إرسال تفاصيل إضافية لتأكيد العملية."

    body = "\n".join(matched_explanations)
    return (
        f"يرجى توضيح بيانات الطلب وإعادة رفع إيصال واضح للأسباب التالية:\n"
        f"{body}"
    )
