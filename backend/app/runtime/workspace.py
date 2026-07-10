"""Per-job workspace + immutable process package layout (01 §4, 04 §2).

Hardening 2026-07-10 (T9): agents are folder-isolated — each writes only its own
agents/<slug>/ subtree; shared/ carries read-only interface specs; the consolidator is the
single cross-folder reader (merge_agent_src). Real isolation is the sandbox MOUNT scope
(codeexec callers pass the narrowest folder), not convention.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from app.config import settings


def job_dir(job_id: str) -> Path:
    d = settings.workspaces_dir / job_id
    (d / "src").mkdir(parents=True, exist_ok=True)
    return d


def agent_dir(job_id: str, slug: str) -> Path:
    """One agent's isolated folder: data/workspaces/<job_id>/agents/<slug>/."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", slug or "agent").strip("-") or "agent"
    d = job_dir(job_id) / "agents" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_files(job_id: str, files: list[dict], agent: str | None = None) -> list[str]:
    """Write files under the job dir, or under agents/<agent>/ when an agent slug is given
    (default keeps the flat wave-1 behavior for compat)."""
    base = agent_dir(job_id, agent) if agent else job_dir(job_id)
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


def write_shared_interfaces(job_id: str, interfaces: list) -> None:
    """Stage 2 publishes the plan's interfaces read-only for all agents (shared/interfaces.json)."""
    d = job_dir(job_id) / "shared"
    d.mkdir(exist_ok=True)
    (d / "interfaces.json").write_text(json.dumps(interfaces, indent=2))


def merge_agent_src(job_id: str) -> list[str]:
    """Consolidation-time merge (the single cross-folder read): agents/*/src/** and each agent's
    root .py files into the job-level src/ tree. Later agents win on collisions — the plan's
    interfaces, not shared paths, are the coordination surface."""
    base = job_dir(job_id)
    merged: list[str] = []
    agents_root = base / "agents"
    if not agents_root.exists():
        return merged
    for adir in sorted(p for p in agents_root.iterdir() if p.is_dir()):
        src = adir / "src"
        if src.exists():
            for p in sorted(src.rglob("*.py")):
                rel = Path("src") / p.relative_to(src)
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, base / rel)
                merged.append(str(rel))
        for p in sorted(adir.glob("*.py")):   # module-root files (e.g. a generated process.py)
            shutil.copyfile(p, base / p.name)
            merged.append(p.name)
    return merged


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
