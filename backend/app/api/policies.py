"""Policy document extraction (Task B). Turns an uploaded policy file into editable text that feeds
the composer's existing `policy_text` path — no change to job creation.

PDFs are parsed locally with pypdf. Images are transcribed through the model router's vision-capable
planner seat as SANITIZED (a policy is a ruleset, not raw customer data), so a judge's BYOK key serves
this path too. Extraction failures return a structured error; the composer keeps the text-file path.
"""
from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import require_demo_token
from app.models.router import router as model_router

router = APIRouter(tags=["policies"])

_MAX_BYTES = 8 * 1024 * 1024      # upload cap; larger => 413
_MAX_EDGE = 1600                  # downscale a vision image's long edge to keep the request cheap
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": {"code": code, "message": msg}})


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()


def _image_data_uri(data: bytes, content_type: str) -> str:
    """Bound the image (long edge <= _MAX_EDGE) so the vision request stays cheap. Falls back to the
    original bytes if Pillow can't decode it."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img.thumbnail((_MAX_EDGE, _MAX_EDGE))
        as_png = img.mode in ("RGBA", "P") or content_type.endswith("png")
        fmt = "PNG" if as_png else "JPEG"
        buf = io.BytesIO()
        (img if as_png else img.convert("RGB")).save(buf, format=fmt)
        data, mime = buf.getvalue(), f"image/{fmt.lower()}"
    except Exception:  # noqa: BLE001 — undecodable: ship the original bytes, let the model try
        mime = content_type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


async def _image_text(data: bytes, content_type: str) -> str:
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "Transcribe the policy text in this image verbatim. Output only the "
         "text content, preserving line breaks and structure. Do not summarize or add commentary."},
        {"type": "image_url", "image_url": {"url": _image_data_uri(data, content_type)}},
    ]}]
    # planner seat is vision-capable and inherits any BYOK override; SANITIZED clears the boundary.
    out = await model_router.complete("planner", messages, scope="system",
                                      data_class="SANITIZED", max_tokens=4096)
    return (out.text or "").strip()


@router.post("/policies/extract", dependencies=[Depends(require_demo_token)])
async def extract_policy(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if not data:
        raise _err(400, "empty file")
    if len(data) > _MAX_BYTES:
        raise _err(413, f"file too large ({len(data) // 1024} KB); cap is {_MAX_BYTES // 1024 // 1024} MB")

    name = (file.filename or "").lower()
    ctype = file.content_type or ""
    try:
        if name.endswith(".pdf") or ctype == "application/pdf":
            text, kind = _pdf_text(data), "pdf"
            if not text:
                raise _err(422, "no extractable text (a scanned PDF? upload the page as an image)")
        elif name.endswith(_IMAGE_EXT) or ctype.startswith("image/"):
            text, kind = await _image_text(data, ctype), "image"
            if not text:
                raise _err(422, "no text returned by the vision model")
        else:
            # plain text is handled client-side; accept it here too as a defensive fallback
            text, kind = data.decode("utf-8", errors="replace").strip(), "text"
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — structured error; composer falls back to the text path
        raise _err(422, f"extraction failed: {type(exc).__name__}: {str(exc)[:200]}") from exc

    return {"text": text, "kind": kind, "name": file.filename or "policy", "chars": len(text)}
