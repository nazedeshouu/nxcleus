"""Policy extraction endpoint (Task B): PDF text via pypdf, image path via the (mock) router with an
OpenAI content-array message, plus the size/empty guards. No network — image runs through mock mode."""
from __future__ import annotations

import io

from httpx import ASGITransport, AsyncClient

from app.api.policies import _image_data_uri, _pdf_text
from app.main import create_app


def _minimal_pdf(text: str) -> bytes:
    """A valid 1-page PDF with one line of extractable text (avoids pulling in reportlab)."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,  # content stream, filled below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 24 Tf 72 700 Td (" + text.encode("latin-1") + b") Tj ET"
    objs[3] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n"
            + str(xref_pos).encode() + b"\n%%EOF")
    return bytes(out)


def _tiny_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_text_extracts():
    assert "Hello Policy" in _pdf_text(_minimal_pdf("Hello Policy"))


def test_image_data_uri_downscales_and_encodes():
    uri = _image_data_uri(_tiny_png(), "image/png")
    assert uri.startswith("data:image/") and ";base64," in uri


async def test_extract_pdf_endpoint():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/policies/extract",
                         files={"file": ("p.pdf", _minimal_pdf("Coverage Rule 7"), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "pdf" and "Coverage Rule 7" in body["text"]


async def test_extract_image_endpoint_mock_router():
    # mock mode (conftest) => planner routes to the mock client; proves the content-array passthrough
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/policies/extract",
                         files={"file": ("scan.png", _tiny_png(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "image" and r.json()["text"]


async def test_extract_empty_and_oversize():
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        empty = await c.post("/api/policies/extract", files={"file": ("e.pdf", b"", "application/pdf")})
        big = await c.post("/api/policies/extract",
                           files={"file": ("big.pdf", b"x" * (8 * 1024 * 1024 + 1), "application/pdf")})
    assert empty.status_code == 400
    assert big.status_code == 413
