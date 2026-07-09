"""Per-job workspace + immutable process package layout (01 §4, 04 §2)."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings


def job_dir(job_id: str) -> Path:
    d = settings.workspaces_dir / job_id
    (d / "src").mkdir(parents=True, exist_ok=True)
    return d


def write_files(job_id: str, files: list[dict]) -> list[str]:
    base = job_dir(job_id)
    written = []
    for f in files:
        rel = f.get("path", "")
        if not rel:
            continue
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.get("content", ""))
        written.append(rel)
    return written


def read_src(job_id: str) -> list[dict]:
    base = job_dir(job_id) / "src"
    out = []
    if base.exists():
        for p in sorted(base.rglob("*.py")):
            out.append({"path": str(p.relative_to(job_dir(job_id))), "content": p.read_text()})
    return out


def package_dir(slug: str, version: int) -> Path:
    d = settings.packages_dir / slug / str(version)
    d.mkdir(parents=True, exist_ok=True)
    return d


def assemble_package(*, slug: str, version: int, manifest: dict, plan: dict, amendments: list,
                     consults: list, goal: dict, src_files: list[dict], tests: list, vectors: list,
                     docs: dict, invoice: dict, topology: dict | None = None) -> str:
    """Write the immutable package directory (04 §2). Returns the package path."""
    root = package_dir(slug, version)
    (root / "plan").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)

    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (root / "plan" / "plan.json").write_text(json.dumps(plan, indent=2))
    (root / "plan" / "amendments.jsonl").write_text("\n".join(json.dumps(a) for a in amendments))
    (root / "plan" / "consults.jsonl").write_text("\n".join(json.dumps(c) for c in consults))
    (root / "plan" / "goal.json").write_text(json.dumps(goal, indent=2))
    for f in src_files:
        target = root / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.get("content", ""))
    if topology is not None:
        (root / "topology.json").write_text(json.dumps(topology, indent=2))
    (root / "tests" / "integration.json").write_text(json.dumps(tests, indent=2))
    (root / "tests" / "vectors.json").write_text(json.dumps(vectors, indent=2))
    (root / "docs" / "README.md").write_text(docs.get("readme", ""))
    (root / "docs" / "runbook.md").write_text(docs.get("runbook", ""))
    (root / "docs" / "qa_report.md").write_text(docs.get("qa_report", ""))
    (root / "invoice.json").write_text(json.dumps(invoice, indent=2))
    return str(root)
