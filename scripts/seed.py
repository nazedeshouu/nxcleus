#!/usr/bin/env python
"""Regenerate every demo seed kit from scratch (09 §2, §5) — the rehearsal-gate command
("seed regenerated from scratch on the VM ... proves no hand-tuned state", 09 §7).

Deterministic (fixed RNG seed in infra/seeds/_gen.py). Writes:
  infra/seeds/out/{bank,clinic,lawfirm}.db  + out/contracts/*.txt   (judge sandbox, Demo 4)
  infra/seeds/out/{exchange,insurer,ledger,freight,market}.db       (extended judge sandbox)
  infra/seeds/out/kyc/{applicants.json, docs/*.png, sanctions/*.csv, pep.json, adverse_media.json}

Run:  uv run --project backend python scripts/seed.py
      (companies only:  ... scripts/seed.py companies)
      (kyc only:        ... scripts/seed.py kyc)
      (one dataset:     ... scripts/seed.py {exchange|insurer|ledger|freight|market})
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from infra.seeds import companies, exchange, freight, insurer, kyc, ledger, market  # noqa: E402

# Extended judge-sandbox datasets: id -> generator (each writes out/<id>.db).
_DATASETS = {"exchange": exchange.gen_exchange, "insurer": insurer.gen_insurer,
             "ledger": ledger.gen_ledger, "freight": freight.gen_freight,
             "market": market.gen_market}


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    report: dict = {}
    if which in ("all", "companies"):
        print("generating judge-sandbox companies (bank / clinic / lawfirm) ...")
        report["companies"] = companies.generate_all()
    for ds_id, gen in _DATASETS.items():
        if which in ("all", ds_id):
            print(f"generating extended dataset ({ds_id}) ...")
            report[ds_id] = gen()
    if which in ("all", "kyc"):
        print("generating KYC hero seed kit (30 applicants + ID docs + sanctions lists) ...")
        report["kyc"] = kyc.generate()
    print(json.dumps(report, indent=1))
    print(f"\nseed complete in {time.time() - t0:.1f}s -> infra/seeds/out/")


if __name__ == "__main__":
    main()
