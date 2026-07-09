"""OCR / document text-extraction seam (03 §2.2).

Structured behind `app/boundary/` on purpose: the trust seat calls `extract_text` and gets text back,
so the eventual trust-multimodal upgrade (droplet Gemma reading the image directly) is a config
change here, not a rewrite of stage 0. Extraction tries, in order:

  1. pytesseract on an image — only when the `tesseract` binary is actually installed (the prod VM;
     the dev box usually has none).
  2. a co-located `<path>.txt` sidecar text layer — the PIL-generated KYC seed docs ship one, so the
     hero demo's OCR path works with zero system dependencies (clean fallback per 03 §2.2).
  3. a PDF text layer via pypdf.

Returns `(text, method)`; `method` feeds the `documents_ocred` telemetry and the UI badge.
"""
from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def extract_text(path: str | Path) -> tuple[str, str]:
    """(text, method). Never raises: an unreadable document yields ("", "none")."""
    p = Path(path)
    ext = p.suffix.lower()

    if ext in _IMAGE_EXT and tesseract_available():
        try:
            import pytesseract
            from PIL import Image

            return pytesseract.image_to_string(Image.open(p)).strip(), "tesseract"
        except Exception:
            pass  # fall through to the sidecar / text-layer path

    sidecar = p.with_suffix(p.suffix + ".txt")   # e.g. applicant_01.png.txt
    if sidecar.exists():
        return sidecar.read_text().strip(), "text-layer"

    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
            return text.strip(), "pdf-text-layer"
        except Exception:
            pass

    if ext == ".txt" and p.exists():
        return p.read_text().strip(), "text"

    return "", "none"


def extract_batch(paths: Iterable[str | Path]) -> list[dict]:
    """OCR a set of document refs; each result carries the method + char count for telemetry."""
    out: list[dict] = []
    for pth in paths:
        text, method = extract_text(pth)
        out.append({"path": str(pth), "text": text, "method": method, "chars": len(text)})
    return out
