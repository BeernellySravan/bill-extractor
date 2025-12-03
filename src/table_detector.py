# src/table_detector.py
from src.ocr import run_ocr_on_image
import numpy as np

def extract_rows_from_ocr(ocr, min_confidence=40):
    """
    Build robust lines with positional info.
    Returns list of dicts:
      { "text": str, "avg_conf": int, "min_left": int, "max_right": int, "words": [ (text,left,conf) ] }
    """
    n = len(ocr.get("text", []))
    words = []
    for i in range(n):
        txt = str(ocr["text"][i]).strip()
        if not txt:
            continue
        try:
            conf = int(float(ocr["conf"][i]))
        except:
            conf = -1
        # skip very low confidence words
        if conf >= 0 and conf < min_confidence:
            continue
        left = int(ocr["left"][i])
        top = int(ocr["top"][i])
        width = int(ocr.get("width", [0]*n)[i]) if "width" in ocr else 0
        right = left + width
        words.append({"text": txt, "left": left, "right": right, "top": top, "conf": conf})

    if not words:
        return []

    # sort by top then left
    words = sorted(words, key=lambda w: (w["top"], w["left"]))

    # group into lines: words with top within threshold -> same line
    lines = []
    current = {"top": words[0]["top"], "words": [words[0]]}
    for w in words[1:]:
        if abs(w["top"] - current["top"]) <= 10:
            current["words"].append(w)
        else:
            lines.append(current)
            current = {"top": w["top"], "words": [w]}
    lines.append(current)

    out_lines = []
    for line in lines:
        ws = sorted(line["words"], key=lambda x: x["left"])
        text = " ".join(w["text"] for w in ws)
        confs = [w["conf"] for w in ws if w["conf"] >= 0]
        avg_conf = int(sum(confs)/len(confs)) if confs else -1
        min_left = min(w["left"] for w in ws)
        max_right = max(w["right"] for w in ws)
        out_lines.append({
            "text": text,
            "avg_conf": avg_conf,
            "min_left": min_left,
            "max_right": max_right,
            "words": ws
        })
    return out_lines 