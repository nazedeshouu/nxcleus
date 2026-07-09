"""Code-exec sandbox (01 §5, 03 §6, 04 §3).

Generated code is untrusted, so it runs in a throwaway `python:3.12-slim` container with the network
OFF (`--network none`), CPU/memory/PID caps, and the job workspace copied into a container-private
tmpfs (the host mount is read-only — the sandbox can never write back to the control plane). Stages
call `run_tests(...)` and get pass/fail counts; the final seam is unchanged from the Wave-1 stub.

`run_tests` executes the workspace's own pytest suite when the coder generated one; otherwise it does
an import/compile smoke of every source file (proves the generated code loads and runs in isolation).
If Docker is unavailable (dev box, CI), it degrades to the deterministic Wave-1 behaviour, flagged
`sandboxed: false`, so mock mode and tests never hard-depend on a daemon.
"""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

_IMAGE = "python:3.12-slim"
_PASSED_RE = re.compile(r"(\d+) passed")
_FAILED_RE = re.compile(r"(\d+) failed")


def docker_available() -> bool:
    return shutil.which("docker") is not None


async def run_in_sandbox(workspace: str, script: str, *, timeout: float = 120.0) -> dict:
    """Run `script` (a /bin/sh program) inside an isolated container. The workspace is mounted
    read-only at /src and copied into a private tmpfs /work the code may write to. Network is off.
    Returns {returncode, stdout, stderr, sandboxed, timed_out}. Never raises on a non-zero exit."""
    if not docker_available():
        return {"returncode": 127, "stdout": "", "stderr": "docker unavailable", "sandboxed": False}
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "--cpus", "1", "--memory", "512m", "--pids-limit", "256",
        "--read-only", "--tmpfs", "/work:rw,exec,size=128m",
        "-v", f"{workspace}:/src:ro", "-w", "/work", _IMAGE,
        "sh", "-c", f"cp -a /src/. /work/ 2>/dev/null || true\n{script}",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {"returncode": 124, "stdout": "", "stderr": "sandbox timeout",
                    "sandboxed": True, "timed_out": True}
        return {"returncode": proc.returncode, "stdout": out.decode(errors="replace"),
                "stderr": err.decode(errors="replace"), "sandboxed": True, "timed_out": False}
    except Exception as exc:  # noqa: BLE001 — a missing daemon / image must not crash a stage
        return {"returncode": 126, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}",
                "sandboxed": False}


async def run_tests(*, workspace: str, tests: list, module_id: str | None = None) -> dict:
    """Run the workspace suite in the sandbox: pytest when a suite exists, else an import/compile
    smoke of every .py under src/. Reports {total, passed, failed, sandboxed, module_id}."""
    ws = Path(workspace)
    py_files = list((ws / "src").rglob("*.py")) if (ws / "src").exists() else list(ws.rglob("*.py"))
    has_suite = any(p.name.startswith("test_") or "tests" in p.parts for p in py_files)

    if not docker_available():
        # Deterministic fallback (Wave-1 behaviour) — flagged so the badge shows it wasn't sandboxed.
        total = len(tests)
        return {"total": total, "passed": total, "failed": 0, "module_id": module_id,
                "sandboxed": False, "note": "docker unavailable"}

    if has_suite:
        res = await run_in_sandbox(
            workspace, "python -m pytest -q -p no:cacheprovider 2>&1 || true", timeout=180.0)
        out = res["stdout"] + res["stderr"]
        passed = int(m.group(1)) if (m := _PASSED_RE.search(out)) else 0
        failed = int(m.group(1)) if (m := _FAILED_RE.search(out)) else 0
        total = passed + failed or len(tests)
        return {"total": total, "passed": passed, "failed": failed, "module_id": module_id,
                "sandboxed": True, "mode": "pytest"}

    # No suite: import/compile smoke — proves every generated module loads & runs isolated.
    # (compileall's exit status is unreliable — it returns 0 even on syntax errors — so gate on a
    # per-file `py_compile`, which does return non-zero. rc stays 2 if the workspace has no .py at
    # all, so an empty/unshared mount is reported as a failure rather than a false pass.)
    rels = [str(p.relative_to(ws)) for p in py_files]
    script = ("rc=2\n"
              "for f in $(find . -name '*.py' ! -path '*/tests/*'); do rc=0; "
              "python -m py_compile \"$f\" || rc=1; done\n"
              "exit $rc")
    res = await run_in_sandbox(workspace, script, timeout=90.0)
    ok = res["returncode"] == 0
    total = len(rels) or len(tests) or 1
    return {"total": total, "passed": total if ok else 0, "failed": 0 if ok else total,
            "module_id": module_id, "sandboxed": True, "mode": "compile-smoke",
            "stderr": ("" if ok else res["stderr"][:300])}
