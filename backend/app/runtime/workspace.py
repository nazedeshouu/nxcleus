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
from app.safe_paths import UnsafePathError, resolve_within


def _generated_source_target(base: Path, relative: str | Path) -> Path:
    """Contain generated package code and keep it out of trusted metadata namespaces."""
    target = resolve_within(base, relative)
    rel = target.relative_to(base.resolve(strict=False))
    is_entrypoint = rel == Path("process.py")
    is_src_python = len(rel.parts) > 1 and rel.parts[0] == "src" and rel.suffix == ".py"
    if not (is_entrypoint or is_src_python):
        raise UnsafePathError("generated package files must be process.py or Python under src/")
    return target


def job_dir(job_id: str) -> Path:
    d = settings.workspaces_dir / job_id
    (d / "src").mkdir(parents=True, exist_ok=True)
    return d


def reset_job(job_id: str) -> None:
    """Remove only one job's generated workspace before rebuilding a corrected request."""
    target = resolve_within(settings.workspaces_dir, job_id)
    if target.exists():
        shutil.rmtree(target)


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
        target = (resolve_within(base, rel) if agent
                  else _generated_source_target(base, rel))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.get("content", ""), encoding="utf-8")
        written.append(str(rel))
    return written


def write_shared_interfaces(job_id: str, interfaces: list) -> None:
    """Stage 2 publishes the plan's interfaces read-only for all agents (shared/interfaces.json)."""
    d = job_dir(job_id) / "shared"
    d.mkdir(exist_ok=True)
    (d / "interfaces.json").write_text(json.dumps(interfaces, indent=2), encoding="utf-8")


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
            out.append({"path": str(p.relative_to(job_dir(job_id))),
                        "content": p.read_text(encoding="utf-8")})
    return out


def _package_path(slug: str, version: int) -> Path:
    return resolve_within(settings.packages_dir, f"{slug}/{version}")


def package_dir(slug: str, version: int) -> Path:
    d = _package_path(slug, version)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validated_generated_sources(root: Path, src_files: list[dict]) -> list[tuple[Path, str]]:
    """Validate every generated path before package creation and reject portable collisions."""
    validated: list[tuple[Path, str]] = []
    seen: set[str] = set()
    root_resolved = root.resolve(strict=False)
    for source in src_files:
        target = _generated_source_target(root, source.get("path", ""))
        collision_key = target.relative_to(root_resolved).as_posix().casefold()
        if collision_key in seen:
            raise UnsafePathError("duplicate generated package path")
        content = source.get("content", "")
        if not isinstance(content, str):
            raise ValueError("generated package content must be text")
        seen.add(collision_key)
        validated.append((target, content))
    return validated


def assemble_package(*, slug: str, version: int, manifest: dict, plan: dict, amendments: list,
                     consults: list, goal: dict, src_files: list[dict], tests: list, vectors: list,
                     docs: dict, invoice: dict, topology: dict | None = None) -> str:
    """Write the immutable package directory (04 §2). Returns the package path."""
    root = _package_path(slug, version)
    validated_sources = _validated_generated_sources(root, src_files)
    root.mkdir(parents=True, exist_ok=True)
    (root / "plan").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)

    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "plan" / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (root / "plan" / "amendments.jsonl").write_text(
        "\n".join(json.dumps(a) for a in amendments), encoding="utf-8")
    (root / "plan" / "consults.jsonl").write_text(
        "\n".join(json.dumps(c) for c in consults), encoding="utf-8")
    (root / "plan" / "goal.json").write_text(json.dumps(goal, indent=2), encoding="utf-8")
    for target, content in validated_sources:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if topology is not None:
        (root / "topology.json").write_text(json.dumps(topology, indent=2), encoding="utf-8")
    (root / "tests" / "integration.json").write_text(
        json.dumps(tests, indent=2), encoding="utf-8")
    (root / "tests" / "vectors.json").write_text(
        json.dumps(vectors, indent=2), encoding="utf-8")
    (root / "docs" / "README.md").write_text(docs.get("readme", ""), encoding="utf-8")
    (root / "docs" / "runbook.md").write_text(docs.get("runbook", ""), encoding="utf-8")
    (root / "docs" / "qa_report.md").write_text(
        docs.get("qa_report", ""), encoding="utf-8")
    (root / "invoice.json").write_text(json.dumps(invoice, indent=2), encoding="utf-8")
    return str(root)
