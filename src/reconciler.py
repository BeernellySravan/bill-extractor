# src/reconciler.py
from decimal import Decimal
import re
from collections import defaultdict
from src.ocr import run_ocr_on_image
from src.table_detector import extract_rows_from_ocr

def normalize_name(n):
    return "".join(ch for ch in n.lower() if ch.isalnum() or ch.isspace()).strip()

def dedupe_items(items):
    seen = {}
    unique = []
    for it in items:
        key = (normalize_name(it.get("item_name","")), round(float(it.get("item_amount",0.0)),2))
        if key in seen:
            continue
        seen[key] = True
        unique.append(it)
    return unique

def find_printed_total_on_pages(pages):
    """
    Given PIL image pages, run OCR text scan to find candidate printed totals.
    Return float or None.
    """
    candidates = []
    for p in pages:
        try:
            ocr = run_ocr_on_image(p)
            lines = extract_rows_from_ocr(ocr, min_confidence=10)
            for ln in lines:
                txt = ln.get("text","")
                low = txt.lower()
                if "total" in low or "amount" in low or "grand total" in low:
                    nums = re.findall(r"\d+[.,]?\d*", txt)
                    if nums:
                        candidates.append(float(nums[-1].replace(",","")))
        except Exception:
            # if OCR of a page fails, skip that page
            continue
    if not candidates:
        return None
    return float(candidates[-1])

def reconcile_totals(page_items, pages=None):
    """
    page_items: list of page dicts (each has 'bill_items' and optionally 'lines')
    pages: optional list of PIL pages (for printed total search)
    Returns dict with reconciled_amount and optional printed_total / note.
    """
    all_items = []
    for page in page_items:
        all_items.extend(page.get("bill_items", []))

    unique = dedupe_items(all_items)
    total_sum = sum(float(i.get("item_amount",0.0)) for i in unique)
    result = {"reconciled_amount": float(Decimal(str(total_sum)))}

    printed = None
    if pages:
        printed = find_printed_total_on_pages(pages)
        if printed is not None:
            result["printed_total"] = float(printed)
            diff = abs(printed - result["reconciled_amount"])
            if diff > max(1.0, 0.01 * (printed if printed else 0.0)):
                result["note"] = f"printed_total_mismatch (printed={printed},extracted={result['reconciled_amount']})"
    return result 