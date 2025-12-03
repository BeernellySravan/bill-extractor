import os
import tempfile
import requests
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
from urllib.parse import urlparse
from src.config import POPPLER_PATH


#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"



def _normalize_local_path(path):
    parsed = urlparse(path)
    if parsed.scheme == "file":
        p = parsed.path or parsed.netloc or ""
        if p.startswith("/") and len(p) > 2 and p[2] == ":":
            p = p.lstrip("/")
        return p
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        return path.lstrip("/")
    return path


def load_document_images(document_path, dpi=300):
    # Normalize path for file:// or raw local paths
    if document_path.startswith("file://") or document_path.startswith("FILE://"):
        document_path = _normalize_local_path(document_path)
    document_path = _normalize_local_path(document_path)

    # If it is a URL, download PDF temporarily
    if str(document_path).lower().startswith(("http://", "https://")):
        resp = requests.get(document_path, stream=True, timeout=60)
        resp.raise_for_status()
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)
        document_path = tmp_path

    # If PDF, convert to images using Poppler
    if document_path.lower().endswith(".pdf"):
        poppler_arg = {"poppler_path": POPPLER_PATH} if POPPLER_PATH else {}
        pages = convert_from_path(document_path, dpi=dpi, **poppler_arg)
        return pages

    # Otherwise assume it is an image
    return [Image.open(document_path).convert("RGB")]


def run_ocr_on_image(image):
    """
    Run Tesseract OCR on a PIL Image and return word-level data.
    """

    # pytesseract now uses the correct tesseract_cmd path above
    return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT) 