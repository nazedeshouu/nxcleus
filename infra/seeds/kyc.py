"""KYC hero seed kit (09 §5, Demo 1).

30 synthetic applicants, each with a generated, OCR-able ID document image (PIL) + a `.txt` sidecar
text layer so the OCR path (app/boundary/ocr.py) works with or without a tesseract binary. Ships the
REAL public OFAC SDN + EU consolidated sanctions lists (downloaded at seed time; graceful fallback to
a synthetic list carrying the planted hit-names if the network is unavailable), plus synthetic
PEP + adverse-media fixtures. Fixed RNG seed → reproducible (rehearsal gate 09 §7).

Applicants are shaped so a correct pipeline produces a spread of decisions: planted sanctions hits,
planted PEPs, an expired document, and a clean majority — never canned outputs, only planted inputs.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from pathlib import Path

import httpx

from ._gen import SANCTIONS_ADJACENT, full_name, rng

OUT = Path(__file__).resolve().parent / "out" / "kyc"

# Public sanctions-list sources (downloaded at seed time on the VM). Legacy flat CSV / consolidated
# XML — stable public endpoints. Network-restricted environments fall back to a synthetic list.
_OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
_OFAC_CONS_CSV = "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv"

_NATIONALITIES = ["US", "GB", "DE", "FR", "AE", "KZ", "RU", "NG", "CN", "BR", "IN", "UA", "TR"]


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _id_image(fields: dict, path: Path) -> None:
    """Render an OCR-able ID card (dark text on a light card) + a `.txt` sidecar with the same text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 400), (238, 240, 244))
    d = ImageDraw.Draw(img)
    d.rectangle([12, 12, 628, 388], outline=(40, 60, 90), width=3)
    title = "PASSPORT" if fields["doc_type"] == "passport" else "NATIONAL IDENTITY CARD"
    d.text((28, 26), f"{fields['issuer']}  —  {title}", fill=(20, 40, 70), font=_font(26))
    d.line([28, 66, 612, 66], fill=(120, 140, 170), width=2)
    lines = [
        ("Surname / Given names", fields["name"]),
        ("Date of birth", fields["dob"]),
        ("Nationality", fields["nationality"]),
        ("Document No.", fields["doc_number"]),
        ("Date of issue", fields["issue"]),
        ("Date of expiry", fields["expiry"]),
    ]
    y = 88
    for label, val in lines:
        d.text((28, y), label.upper(), fill=(90, 100, 120), font=_font(15))
        d.text((28, y + 20), str(val), fill=(15, 20, 35), font=_font(24))
        y += 52
    img.save(path)
    # sidecar text layer for the no-tesseract OCR fallback
    sidecar = "\n".join([f"{title}", f"Issuer: {fields['issuer']}"]
                        + [f"{label}: {val}" for label, val in lines])
    path.with_suffix(path.suffix + ".txt").write_text(sidecar)


def _download_or_synth(url: str, out_path: Path, synth_rows: list[list[str]]) -> dict:
    """Best-effort real download; fall back to a synthetic CSV carrying the planted hit-names."""
    try:
        r = httpx.get(url, timeout=20.0, follow_redirects=True)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return {"source": "downloaded", "url": url, "bytes": len(r.content)}
    except Exception as exc:  # noqa: BLE001 — offline seed still needs a usable list
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ent_num", "name", "type", "program", "list"])
        for row in synth_rows:
            w.writerow(row)
        out_path.write_text(buf.getvalue())
        return {"source": "synthetic-fallback", "reason": type(exc).__name__, "rows": len(synth_rows)}


def generate(n: int = 30) -> dict:
    r = rng(7)
    OUT.mkdir(parents=True, exist_ok=True)
    docs_dir = OUT / "docs"
    docs_dir.mkdir(exist_ok=True)
    for old in docs_dir.glob("*"):
        old.unlink()

    applicants, hits, peps, expired = [], 0, 0, 0
    for i in range(1, n + 1):
        # ~5 planted sanctions hits (names from the adjacency pool), ~4 PEPs, ~2 expired docs
        planted_hit = i <= 5
        name = SANCTIONS_ADJACENT[(i - 1) % len(SANCTIONS_ADJACENT)] if planted_hit else full_name(r)
        is_pep = (not planted_hit) and (5 < i <= 9)
        expiry_d = (date(2026, 7, 9) - timedelta(days=r.randint(30, 400))) if i in (10, 11) else \
            (date(2026, 7, 9) + timedelta(days=r.randint(200, 3000)))
        doc_type = r.choice(["passport", "id_card"])
        nat = r.choice(_NATIONALITIES)
        dob_d = date(2026, 7, 9) - timedelta(days=r.randint(20 * 365, 75 * 365))
        issue_d = expiry_d - timedelta(days=3650)
        rec = {
            "applicant_id": f"APP-{i:03d}",
            "name": name,
            "dob": dob_d.isoformat(),
            "nationality": nat,
            "issuer": {"passport": nat, "id_card": nat}[doc_type],
            "doc_type": doc_type,
            "doc_number": f"{nat}{r.randint(1000000, 9999999)}",
            "issue": issue_d.isoformat(),
            "expiry": expiry_d.isoformat(),
            "account": f"{r.randint(4000,4999)} {r.randint(1000,9999)} {r.randint(1000,9999)} {r.randint(1000,9999)}",
            "email": f"{name.split()[0].lower()}.{name.split()[-1].lower()}@example.com",
            "planted": ("sanctions_hit" if planted_hit else "pep" if is_pep
                        else "expired_document" if i in (10, 11) else "clean"),
        }
        _id_image(rec, docs_dir / f"{rec['applicant_id']}.png")
        rec["doc_image"] = f"docs/{rec['applicant_id']}.png"
        applicants.append(rec)
        hits += planted_hit
        peps += is_pep
        expired += 1 if i in (10, 11) else 0
    (OUT / "applicants.json").write_text(json.dumps(applicants, indent=1))

    # sanctions lists — real download, else synthetic containing the planted hit-names
    sanc_dir = OUT / "sanctions"
    sanc_dir.mkdir(exist_ok=True)
    synth = [[str(1000 + i), nm, "individual", "SDN", "SDN List"] for i, nm in enumerate(SANCTIONS_ADJACENT)]
    ofac = _download_or_synth(_OFAC_SDN_CSV, sanc_dir / "ofac_sdn.csv", synth)
    eu = _download_or_synth(_OFAC_CONS_CSV, sanc_dir / "eu_consolidated.csv", synth)

    # PEP + adverse-media fixtures (synthetic) — names that should trip the PEP/adverse screen
    pep_names = [a["name"] for a in applicants if a["planted"] == "pep"]
    (OUT / "pep.json").write_text(json.dumps(
        [{"name": nm, "role": r.choice(["Deputy Minister", "State Bank Director", "MP", "Mayor"]),
          "country": r.choice(_NATIONALITIES), "since": 2018 + r.randint(0, 6)} for nm in pep_names], indent=1))
    (OUT / "adverse_media.json").write_text(json.dumps(
        [{"name": nm, "headline": f"Regulator opens inquiry into {nm.split()[-1]} affiliate",
          "source": "synthetic-wire", "sentiment": "negative"} for nm in pep_names[:2]], indent=1))

    return {"applicants": len(applicants),
            "planted": {"sanctions_hits": hits, "peps": peps, "expired_documents": expired,
                        "clean": len(applicants) - hits - peps - expired},
            "docs": len(list(docs_dir.glob("*.png"))),
            "ofac_sdn": ofac, "eu_consolidated": eu}
