# src/lineitem_extractor.py
"""
Flexible extractor (Option B) with stricter noise filtering and safer name+amount rules.
Replace your existing file with this one.
"""
import re
import statistics
import typing
from src.ocr import run_ocr_on_image
from src.table_detector import extract_rows_from_ocr
from src.utils import parse_money

DEBUG = True

BLACKLIST_KEYWORDS = [
    "total", "subtotal", "sub total", "grand total", "gst", "tax", "invoice", "bill", "page",
    "round off", "net amount", "amount due", "phone", "tel", "mobile", "date", "ref"
]

JSON_LIKE_PATTERNS = [
    r'\"[^\"]+\"\s*:',
    r'^\s*[\{\}\[\]]',
    r'\b"is success"\b',
    r'\b"data"\b',
    r'\b"pagewise line items"\b',
    r'\b"item name"\b',
    r'\b"item amount"\b',
    r'\b"item rate"\b',
    r'\b"item quantity"\b',
]

AMOUNT_TOLERANCE = 55
MIN_NAME_ALPHA = 3   # tighten: require at least 3 alphabetic chars in final name

def _debug(*args):
    if DEBUG:
        print(*args)


def looks_like_total_line(text_lc):
    for kw in BLACKLIST_KEYWORDS:
        if kw in text_lc:
            return True
    # If line is purely numeric tokens (likely totals/indices), treat as total/footer
    if re.fullmatch(r"[\d\.,\s]+", text_lc):
        return True
    return False


def _estimate_amount_column(lines):
    rightmost_lefts = []
    for ln in lines:
        if not ln.get("words"):
            continue
        w = ln["words"][-1]
        rightmost_lefts.append(w["left"])
    if not rightmost_lefts:
        return None
    try:
        med = int(statistics.median(rightmost_lefts))
    except Exception:
        med = rightmost_lefts[len(rightmost_lefts) // 2]
    return med


def _is_price_token(tok):
    tok = str(tok).strip().replace(",", "").replace(" ", "")
    return bool(re.match(r'^[₹$€£]?\d+(\.\d{1,2})?$', tok))


def _strip_trailing_number_chars(text):
    t = re.sub(r'[\d\.,\s₹$€£:]+$', "", text).strip()
    t = re.sub(r'\"[^\"]*\"$', "", t).strip()
    t = t.rstrip('":,{}[] ')
    return t.strip()


def _clean_name_from_json_noise(text):
    cleaned = re.sub(r'\"[^\"]+\"\s*:\s*', '', text)
    cleaned = cleaned.replace('{', '').replace('}', '')
    cleaned = cleaned.replace('[', '').replace(']', '')
    cleaned = cleaned.replace('"', '')
    cleaned = re.sub(r'\b(item|amount|rate|quantity|is success|data|pagewise|line items)\b', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _parse_candidate_amount(token_text):
    nums = re.findall(r"\d+[.,]?\d*", token_text)
    return parse_money(nums[-1]) if nums else parse_money(token_text)


# ----------------- header/footer & noise filters -----------------
_HEADER_FOOTER_KEYWORDS = [
    "sample document", "description qty", "qty / hrs", "page", "printed on",
    "request format", "document\":", "http", "https", "sample", "printed on",
    "page of", "printed on :", "of", "printed", "sample 1", "sample 2", "sample 3"
]

_AMT_CANDIDATE_RE = re.compile(r'[-+]?\d{1,3}(?:[,.\s]\d{3})*(?:\.\d{1,2})?$')

def looks_like_header_footer(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    for k in _HEADER_FOOTER_KEYWORDS:
        if k in t:
            return True
    if t.startswith("http") or "%" in t or "sv=" in t:
        return True
    # Reject tiny alphabetic tokens like "Page"
    if len(t) <= 4 and t.isalpha():
        return True
    return False

def filter_header_footer_lines(raw_lines: typing.List[typing.Union[str, dict]]):
    """
    Remove obvious headers/footers and short page-number tokens from OCR lines.
    raw_lines: list of dicts (with 'text') or strings
    """
    out = []
    for ln in raw_lines:
        text = ln.get("text", "") if isinstance(ln, dict) else str(ln)
        txt = text.strip()
        if not txt:
            continue
        # drop obvious header/footer patterns
        if looks_like_header_footer(txt):
            continue
        # drop single-token numeric page numbers (1, 2, 09, etc)
        toks = txt.split()
        if len(toks) == 1 and toks[0].isdigit() and len(toks[0]) <= 3:
            continue
        # drop things that look like timestamps or long query strings
        if re.search(r'\d{2}[:/]\d{2}|\d{4}-\d{2}-\d{2}|%3A|sv=', txt):
            continue
        out.append(ln)
    return out

# --------- split merged lines -------------
SPLIT_ITEM_RE = re.compile(
    r'\s*(?P<name>.*?)\s+(?P<qty>\d+[.,]?\d*)\s+(?P<rate>\d+[.,]?\d*)(?:\s+\d+[.,]?\d*)?\s+(?P<amount>\d+[.,]?\d*)(?=\s|$)',
    flags=re.IGNORECASE)

def split_merged_line(raw_text):
    results = []
    for m in SPLIT_ITEM_RE.finditer(raw_text):
        name = m.group('name').strip()
        qty = parse_money(m.group('qty'))
        rate = parse_money(m.group('rate'))
        amount = parse_money(m.group('amount'))
        name = _clean_name_from_json_noise(name)
        name = _strip_trailing_number_chars(name)
        if name and amount > 0:
            results.append({
                "item_name": name,
                "item_quantity": float(qty),
                "item_rate": float(rate),
                "item_amount": float(amount),
                "confidence": 90,
                "origin": "split_line"
            })
    return results

# ------------------ JSON-like parsing ------------------

def parse_json_like_records_from_lines(lines):
    texts = [ln.get("text", "").strip() for ln in lines]
    items = []
    for idx, txt in enumerate(texts):
        if re.search(r'\"?item\s*name\"?\s*[:=]', txt, flags=re.I):
            m = re.search(r'[:=]\s*["\']?(.*?)[",}]?$', txt)
            name_val = None
            if m:
                name_val = m.group(1).strip()
            else:
                if idx + 1 < len(texts):
                    name_val = texts[idx + 1].strip()
            amount = None
            rate = 0.0
            qty = 0.0
            for j in range(idx, min(idx + 7, len(texts))):
                t = texts[j]
                m_amt = re.search(r'\"?item\s*amount\"?\s*[:=]\s*([0-9\.,]+)', t, flags=re.I)
                if m_amt:
                    amount = _parse_candidate_amount(m_amt.group(1))
                    continue
                m_num = re.fullmatch(r'[\s₹$€£]*([0-9\.,]+)\s*[,]?', t)
                if m_num and amount is None:
                    amount = _parse_candidate_amount(m_num.group(1))
                    continue
                m_rate = re.search(r'\"?item\s*rate\"?\s*[:=]\s*([0-9\.,]+)', t, flags=re.I)
                if m_rate:
                    rate = _parse_candidate_amount(m_rate.group(1))
                m_qty = re.search(r'\"?item\s*quantity\"?\s*[:=]\s*([0-9\.,]+)', t, flags=re.I)
                if m_qty:
                    qty = _parse_candidate_amount(m_qty.group(1))
            if name_val:
                clean_name = _clean_name_from_json_noise(name_val)
                if clean_name and amount and amount > 0:
                    items.append({
                        "item_name": clean_name,
                        "item_quantity": float(qty),
                        "item_rate": float(rate),
                        "item_amount": float(amount),
                        "confidence": 90,
                        "origin": "json_mode"
                    })
    return items

# ------------------ Visual extractor (Flexible, safer rules) ------------------

def conservative_extract_from_lines_with_split_support(lines, amount_col_x, min_confidence=40):
    items = []
    last_item = None
    n = len(lines)
    i = 0

    def looks_like_money_token(tok):
        if not tok:
            return False
        s = str(tok).strip()
        digits = re.sub(r'\D', '', s)
        # must contain decimal/delimiter OR be reasonably large (>= 3 digits)
        if ',' in s or '.' in s:
            return True
        if len(digits) >= 3:
            return True
        return False

    while i < n:
        ln = lines[i]
        raw_text = ln.get("text", "").strip()
        _debug("LINE", i + 1, ":", raw_text)
        if not raw_text or ln.get("avg_conf", -1) < min_confidence:
            last_item = None
            i += 1
            continue

        # split merged lines first (explicit qty+rate+amount all present)
        splits = split_merged_line(raw_text)
        if splits:
            _debug("SPLIT merged line into", len(splits), "items")
            for s in splits:
                items.append(s)
            last_item = None
            i += 1
            continue

        # skip JSON-like noise lines
        json_like = False
        for pat in JSON_LIKE_PATTERNS:
            if re.search(pat, raw_text, flags=re.I):
                json_like = True
                break
        if json_like:
            last_item = None
            i += 1
            continue

        text_lc = raw_text.lower()
        if looks_like_total_line(text_lc):
            last_item = None
            i += 1
            continue

        words = ln.get("words", [])
        if not words:
            last_item = None
            i += 1
            continue

        # candidate 1: rightmost token is price and near amount column
        rightmost = words[-1]
        right_text = rightmost.get("text", "").strip()
        right_left = rightmost.get("left", 0)
        is_price_here = _is_price_token(right_text)
        close_here = (amount_col_x is None) or (abs(right_left - amount_col_x) <= AMOUNT_TOLERANCE)

        amount_used = None
        name_used = None
        qty = 0.0
        rate = 0.0

        if is_price_here and close_here:
            amount_used = _parse_candidate_amount(right_text)
            # attempt to get qty/rate from line numeric tokens
            numeric_tokens = re.findall(r"\d+[.,]?\d*", raw_text)
            if len(numeric_tokens) >= 2:
                rate = parse_money(numeric_tokens[-2])
            if len(numeric_tokens) >= 3:
                qty = parse_money(numeric_tokens[-3])
            name_candidate = _clean_name_from_json_noise(raw_text)
            name_used = _strip_trailing_number_chars(name_candidate)
            _debug("ACCEPT direct:", name_used, amount_used)
        else:
            # candidate 2: next line numeric-only and aligned AND looks like money token (dot/comma or >=3 digits)
            if i + 1 < n:
                next_ln = lines[i + 1]
                next_text = next_ln.get("text", "").strip()
                if re.fullmatch(r'[\d\.,\s₹$€£]+', next_text):
                    if looks_like_money_token(next_text):
                        next_words = next_ln.get("words", [])
                        if next_words:
                            next_right = next_words[-1]
                            next_left = next_right.get("left", 0)
                            close_next = (amount_col_x is None) or (abs(next_left - amount_col_x) <= AMOUNT_TOLERANCE)
                            if close_next:
                                amount_used = _parse_candidate_amount(next_text)
                                # attempt to get qty/rate from raw_text numeric tokens
                                numeric_tokens = re.findall(r"\d+[.,]?\d*", raw_text)
                                if len(numeric_tokens) >= 1:
                                    # if raw_text has numeric tokens, treat them as qty/rate candidates
                                    if len(numeric_tokens) >= 2:
                                        rate = parse_money(numeric_tokens[-1])
                                    if len(numeric_tokens) >= 3:
                                        qty = parse_money(numeric_tokens[-2])
                                name_candidate = _clean_name_from_json_noise(raw_text)
                                name_used = _strip_trailing_number_chars(name_candidate)
                                _debug("ACCEPT split:", name_used, amount_used, "from next line", i + 2)
                                i += 1  # consume next line

        # NOTE: WE DO NOT USE A WEAK FALLBACK (last numeric token) ANYMORE.
        # This prevents page numbers/timestamps being mistaken for amounts.

        # If we found an amount but there was NO qty/rate parsed, enforce stricter money appearance for name+amount lines
        if amount_used and amount_used > 0 and (qty == 0.0 and rate == 0.0):
            # require money-like token (comma/dot OR >=3 digits)
            # and require name to have at least MIN_NAME_ALPHA alphabetic chars and not be noise
            if not looks_like_money_token(str(amount_used)):
                _debug("DROP (amount not money-like):", name_used, amount_used)
                amount_used = None
            else:
                # tighten name checks
                clean_name_alpha = re.sub(r'[^A-Za-z]+', '', (name_used or ""))
                nl = (name_used or "").lower()
                NOISE_WORDS = ["sample document", "sample", "description", "page", "printed on", "request format", "http", "https", "sv=", "%3a", "document"]
                if any(k in nl for k in NOISE_WORDS):
                    _debug("DROP (noise word in name):", name_used, amount_used)
                    amount_used = None
                elif len(clean_name_alpha) < MIN_NAME_ALPHA:
                    _debug("DROP (name lacks alpha chars):", name_used, amount_used)
                    amount_used = None

        if amount_used and amount_used > 0:
            name_alpha = re.sub(r"[^A-Za-z]+", "", name_used or "")
            # require at least MIN_NAME_ALPHA alphabetic chars
            if len(name_alpha) >= MIN_NAME_ALPHA:
                item = {
                    "item_name": name_used if name_used else raw_text,
                    "item_quantity": float(qty),
                    "item_rate": float(rate),
                    "item_amount": float(amount_used),
                    "confidence": int(ln.get("avg_conf", -1)) if ln.get("avg_conf") is not None else -1,
                    "origin": "visual"
                }
                items.append(item)
                last_item = item
            else:
                _debug("REJECT short name after cleaning:", name_used)
                last_item = None
        else:
            # no amount found for this line; maybe continuation of previous item name
            if last_item:
                try:
                    left_cur = ln.get("min_left", 9999)
                    if left_cur <= 300:
                        cont_text = _clean_name_from_json_noise(raw_text)
                        last_item["item_name"] = (last_item["item_name"] + " " + cont_text).strip()
                        last_item["confidence"] = int((last_item.get("confidence", 0) + ln.get("avg_conf", 0)) // 2)
                    else:
                        last_item = None
                except Exception:
                    last_item = None
            else:
                last_item = None
        i += 1

    # debug summary: print extracted items + total
    try:
        total = sum(float(it.get("item_amount", 0.0)) for it in items)
        _debug("EXTRACTED ITEMS COUNT:", len(items), "SUM AMOUNT:", total)
        for it in items[:16]:
            _debug("  ITEM:", it.get("item_name"), it.get("item_amount"))
    except Exception:
        pass

    return items


# ------------------ Main page extractor ------------------

def extract_pagewise_line_items(img, page_no="1", conservative_min_conf=40):
    ocr = run_ocr_on_image(img)
    lines = extract_rows_from_ocr(ocr, min_confidence=10)
    if not lines:
        return {"page_no": page_no, "page_type": "Bill Detail", "bill_items": [], "lines": lines}

    # apply header/footer & noise filter BEFORE any parsing
    lines = filter_header_footer_lines(lines)

    # detect whether page looks JSON-like
    json_like_count = 0
    for ln in lines:
        t = ln.get("text", "")
        for pat in JSON_LIKE_PATTERNS:
            if re.search(pat, t, flags=re.I):
                json_like_count += 1
                break

    items = []
    if json_like_count >= max(3, len(lines) // 6):
        _debug("JSON-like page detected, parsing JSON-like records")
        items = parse_json_like_records_from_lines(lines)
        visual = conservative_extract_from_lines_with_split_support(lines, _estimate_amount_column(lines),
                                                                  min_confidence=conservative_min_conf)
        items.extend(visual)
    else:
        items = conservative_extract_from_lines_with_split_support(lines, _estimate_amount_column(lines),
                                                                  min_confidence=conservative_min_conf)

    # ---------------- stricter post-clean and dedupe ----------------
    clean = []
    seen = set()
    NOISE_WORDS = ["sample document", "sample", "description", "page", "printed on", "request format", "http", "https", "sv=", "%3A", "document"]

    for it in items:
        try:
            amt = float(it.get("item_amount", 0.0))
        except Exception:
            continue
        if amt <= 0:
            continue

        name = it.get("item_name", "").strip()
        nl = name.lower()

        # drop obvious header/footer / url / sample noise
        if any(k in nl for k in NOISE_WORDS):
            _debug("DROPPING noise item:", name, amt)
            continue

        # require at least 3 alphabetic chars in the name (reject "1", "09", "2025")
        if len(re.sub(r'[^a-z]', '', nl)) < MIN_NAME_ALPHA:
            _debug("DROPPING short-alpha name:", name)
            continue

        # normalize for dedupe: amount + first 14 alphanumeric chars of the name
        norm_name = re.sub(r'[^a-z0-9]', '', nl)[:14]
        key = (round(amt, 2), norm_name)

        if key in seen:
            _debug("DUPLICATE drop:", name, amt)
            continue
        seen.add(key)

        it["item_name"] = name
        clean.append(it)

    # return cleaned items
    return {"page_no": page_no, "page_type": "Bill Detail", "bill_items": clean, "lines": lines} 