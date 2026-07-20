"""Fail-closed verification for generated Python workspaces.

Generated source is always parsed on the control-plane host, but is never imported or executed
there. Runtime verification happens only inside the dedicated, network-disabled Docker image.
When Docker itself is unavailable, a syntactically valid workspace is explicitly ``unverified``;
it is never converted into a synthetic pass.
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path, PurePosixPath

from app.config import settings

_PASSED_RE = re.compile(r"(?:^|\s)(\d+) passed(?:\s|,|$)")
_FAILED_RE = re.compile(r"(?:^|\s)(\d+) failed(?:\s|,|$)")
_DOCKER_PROBE_TIMEOUT_S = 3.0
_DOCKER_CACHE_TTL_S = 5.0
_CONTAINER_CLEANUP_TIMEOUT_S = 10.0
_SANDBOX_UID = 65532
_docker_cache_lock = threading.Lock()
_docker_cache_value: bool | None = None
_docker_cache_expires_at = 0.0
_host_data_source_cache: dict[tuple[str, str], str] = {}
_host_data_source_lock = asyncio.Lock()

_IMPORT_SMOKE_SCRIPT = r'''python - <<'PY'
import importlib
import pathlib
import sys

root = pathlib.Path.cwd()
sys.path.insert(0, str(root))
files = []
entrypoint = root / "process.py"
if entrypoint.is_file():
    files.append(entrypoint)
src = root / "src"
if src.is_dir():
    files.extend(sorted(
        path for path in src.rglob("*.py")
        if not path.name.startswith("test_") and "tests" not in path.relative_to(src).parts
    ))
if not files:
    raise RuntimeError("workspace contains no importable Python modules")
for path in files:
    parts = list(path.relative_to(root).parts)
    if path.name == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = path.stem
    if not parts or any(not part.isidentifier() for part in parts):
        raise ImportError(f"invalid Python module path: {path.relative_to(root)}")
    importlib.import_module(".".join(parts))
PY'''


def _probe_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(  # noqa: S603 - fixed executable and arguments
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=_DOCKER_PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and bool(probe.stdout.strip())


def _reset_docker_availability_cache() -> None:
    """Clear the short-lived probe cache (used by tests and explicit health refreshes)."""
    global _docker_cache_expires_at, _docker_cache_value
    with _docker_cache_lock:
        _docker_cache_value = None
        _docker_cache_expires_at = 0.0


def docker_available() -> bool:
    """Cached synchronous Docker CLI + daemon readiness probe."""
    global _docker_cache_expires_at, _docker_cache_value
    now = time.monotonic()
    with _docker_cache_lock:
        if _docker_cache_value is not None and now < _docker_cache_expires_at:
            return _docker_cache_value
        value = _probe_docker()
        _docker_cache_value = value
        _docker_cache_expires_at = time.monotonic() + _DOCKER_CACHE_TTL_S
        return value


async def docker_available_async() -> bool:
    """Probe without ever blocking the asyncio engine on a slow or dead daemon."""
    return await asyncio.to_thread(docker_available)


def unverified_demo_delivery_allowed() -> bool:
    """The escape hatch is effective only in deterministic mock/demo mode."""
    return settings.model_mode == "mock" and settings.allow_unverified_demo_delivery


def _python_files(ws: Path) -> list[Path]:
    return sorted(p for p in ws.rglob("*.py") if p.is_file())


def _static_errors(ws: Path, py_files: list[Path]) -> list[dict[str, str]]:
    """Parse every Python file as UTF-8 without importing or executing generated code."""
    errors: list[dict[str, str]] = []
    for path in py_files:
        rel = path.relative_to(ws).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=rel)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})
    return errors


def _result(
    *,
    verification: str,
    total: int,
    passed: int,
    failed: int,
    module_id: str | None,
    sandboxed: bool,
    reason: str,
    mode: str,
    **extra,
) -> dict:
    return {
        "verification": verification,
        "total": total,
        "passed": passed,
        "failed": failed,
        "module_id": module_id,
        "sandboxed": sandboxed,
        "reason": reason,
        "mode": mode,
        **extra,
    }


async def _force_remove_container(name: str) -> bool:
    """Best-effort removal by trusted internal name; true means Docker found the container."""
    try:
        cleanup = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(cleanup.wait(), timeout=_CONTAINER_CLEANUP_TIMEOUT_S)
        return cleanup.returncode == 0
    except (OSError, asyncio.SubprocessError, TimeoutError):
        return False


def _trusted_workspace(workspace: str) -> tuple[Path | None, str | None]:
    """Resolve an existing workspace strictly below the configured trusted workspace root."""
    try:
        trusted_root = settings.workspaces_dir.resolve(strict=True)
        candidate = Path(workspace).resolve(strict=True)
        candidate.relative_to(trusted_root)
    except (OSError, ValueError) as exc:
        return None, f"workspace is outside the trusted workspace root: {exc}"
    if candidate == trusted_root or not candidate.is_dir():
        return None, "workspace must be an existing directory below the trusted workspace root"
    return candidate, None


def _running_in_container() -> bool:
    return Path("/.dockerenv").is_file()


async def _inspect_host_data_source(container_id: str, destination: str) -> tuple[str | None, str | None]:
    """Resolve the host source backing this container's trusted data mount."""
    key = (container_id, destination)
    if cached := _host_data_source_cache.get(key):
        return cached, None
    async with _host_data_source_lock:
        if cached := _host_data_source_cache.get(key):
            return cached, None
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, asyncio.SubprocessError) as exc:
            return None, f"could not inspect API container mounts: {type(exc).__name__}: {exc}"
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except TimeoutError as exc:
            await _kill_cli_process(proc)
            return None, f"could not inspect API container mounts: {type(exc).__name__}: {exc}"
        except asyncio.CancelledError:
            await asyncio.shield(_kill_cli_process(proc))
            raise
        if proc.returncode != 0:
            detail = err.decode("utf-8", errors="replace")[-300:]
            return None, f"could not inspect API container mounts: {detail or 'docker inspect failed'}"
        try:
            records = json.loads(out.decode("utf-8"))
            if not isinstance(records, list) or len(records) != 1:
                raise ValueError("docker inspect did not return exactly one container")
            mounts = records[0].get("Mounts", [])
            matches = [mount for mount in mounts if mount.get("Destination") == destination]
            if len(matches) != 1:
                raise ValueError("trusted data mount is missing or ambiguous")
            source = matches[0].get("Source")
            if not isinstance(source, str) or not PurePosixPath(source).is_absolute():
                raise ValueError("trusted data mount has no absolute host source")
        except (AttributeError, TypeError, ValueError) as exc:
            return None, f"could not map trusted data mount: {exc}"
        _host_data_source_cache[key] = source
        return source, None


async def _kill_cli_process(proc) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):  # noqa: BLE001 - bounded best-effort process reap
        await asyncio.wait_for(proc.wait(), timeout=_CONTAINER_CLEANUP_TIMEOUT_S)


async def _workspace_mount_args(workspace: Path) -> tuple[list[str] | None, str | None]:
    """Translate a trusted in-container workspace to the exact daemon-host subdirectory."""
    if not _running_in_container():
        return _bind_mount_args(str(workspace))

    data_root = settings.data_path.resolve(strict=True)
    try:
        relative = workspace.relative_to(data_root)
    except ValueError:
        return None, "trusted workspace is not below the configured data mount"
    source, error = await _inspect_host_data_source(socket.gethostname(), str(data_root))
    if error or source is None:
        return None, error or "trusted data mount could not be resolved"
    host_workspace = str(PurePosixPath(source).joinpath(*relative.parts))
    return _bind_mount_args(host_workspace)


def _bind_mount_args(source: str) -> tuple[list[str] | None, str | None]:
    if any(char in source for char in (",", "\n", "\r")):
        return None, "resolved host workspace path is not safe for a Docker mount"
    return ["--mount", f"type=bind,src={source},dst=/src,readonly"], None


async def _stop_cli_and_container(proc, name: str) -> bool:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):  # noqa: BLE001 - cleanup must continue to daemon removal
        await asyncio.wait_for(proc.wait(), timeout=_CONTAINER_CLEANUP_TIMEOUT_S)
    return await _force_remove_container(name)


async def run_in_sandbox(workspace: str, script: str, *, timeout: float = 120.0) -> dict:
    """Run a shell script as an unprivileged user in a network-disabled worker container."""
    trusted_workspace, workspace_error = _trusted_workspace(workspace)
    if workspace_error or trusted_workspace is None:
        return {
            "returncode": 126,
            "stdout": "",
            "stderr": workspace_error or "workspace containment failed",
            "sandboxed": False,
            "timed_out": False,
        }
    if not await docker_available_async():
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": "docker CLI or daemon unavailable",
            "sandboxed": False,
            "timed_out": False,
        }

    mount_args, mount_error = await _workspace_mount_args(trusted_workspace)
    if mount_error or mount_args is None:
        return {
            "returncode": 126,
            "stdout": "",
            "stderr": mount_error or "workspace mount mapping failed",
            "sandboxed": False,
            "timed_out": False,
        }

    container_name = f"nxcleus-codeexec-{uuid.uuid4().hex}"
    uid = str(_SANDBOX_UID)
    cmd = [
        "docker", "run", "--rm", "--pull=never", "--name", container_name,
        "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true", "--user", f"{uid}:{uid}",
        "--cpus", "1", "--memory", "512m", "--pids-limit", "256",
        "--read-only", "--tmpfs",
        f"/work:rw,noexec,nosuid,nodev,size=128m,uid={uid},gid={uid},mode=0700",
        "--env", "HOME=/work", "--env", "TMPDIR=/work/.tmp",
        *mount_args, "-w", "/work", settings.codeexec_image,
        "sh", "-c", f"set -eu\nmkdir -p /work/.tmp\ncp -R /src/. /work/\n{script}",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except (OSError, asyncio.SubprocessError) as exc:
        return {
            "returncode": 126,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "sandboxed": False,
            "timed_out": False,
        }

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        removed = await _stop_cli_and_container(proc, container_name)
        return {
            "returncode": 124,
            "stdout": "",
            "stderr": "sandbox timeout",
            "sandboxed": removed,
            "timed_out": True,
        }
    except asyncio.CancelledError:
        await asyncio.shield(_stop_cli_and_container(proc, container_name))
        raise

    # Docker reserves 125 for a CLI/daemon failure before the container command ran.
    sandboxed = proc.returncode != 125
    return {
        "returncode": proc.returncode,
        "stdout": out.decode("utf-8", errors="replace"),
        "stderr": err.decode("utf-8", errors="replace"),
        "sandboxed": sandboxed,
        "timed_out": False,
    }


async def run_tests(*, workspace: str, tests: list, module_id: str | None = None) -> dict:
    """Return an explicit ``passed``, ``failed``, or ``unverified`` verification result."""
    ws, workspace_error = _trusted_workspace(workspace)
    if workspace_error or ws is None:
        return _result(
            verification="failed", total=1, passed=0, failed=1, module_id=module_id,
            sandboxed=False, reason=workspace_error or "workspace containment failed",
            mode="workspace-validation",
        )
    py_files = _python_files(ws)
    if not py_files:
        return _result(
            verification="failed", total=1, passed=0, failed=1, module_id=module_id,
            sandboxed=False, reason="workspace contains no Python files", mode="static-parse",
            static_errors=[],
        )

    static_errors = _static_errors(ws, py_files)
    if static_errors:
        return _result(
            verification="failed", total=len(py_files), passed=0,
            failed=len(static_errors), module_id=module_id, sandboxed=False,
            reason="static Python parsing failed", mode="static-parse",
            static_errors=static_errors,
        )

    has_suite = any(
        path.name.startswith("test_") or path.name.endswith("_test.py")
        for path in py_files
    )
    if not await docker_available_async():
        return _result(
            verification="unverified", total=0, passed=0, failed=0,
            module_id=module_id, sandboxed=False,
            reason="Docker CLI or daemon unavailable; static parsing passed but code was not executed",
            mode="pytest" if has_suite else "import-smoke",
        )

    if has_suite:
        res = await run_in_sandbox(
            workspace, "python -m pytest -q -p no:cacheprovider", timeout=180.0)
        output = f"{res.get('stdout', '')}\n{res.get('stderr', '')}"
        if not res.get("sandboxed"):
            return _result(
                verification="unverified", total=0, passed=0, failed=0,
                module_id=module_id, sandboxed=False,
                reason="Docker was reachable but the pytest worker container did not start",
                mode="pytest", returncode=res.get("returncode"), output=output[-1000:],
            )
        passed_match = _PASSED_RE.search(output)
        failed_match = _FAILED_RE.search(output)
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        summary_found = passed_match is not None or failed_match is not None
        ok = bool(res.get("sandboxed")) and res.get("returncode") == 0 and summary_found and failed == 0
        if ok:
            return _result(
                verification="passed", total=passed, passed=passed, failed=0,
                module_id=module_id, sandboxed=True, reason="pytest passed", mode="pytest",
            )
        reported_failed = failed or 1
        return _result(
            verification="failed", total=passed + reported_failed, passed=passed,
            failed=reported_failed, module_id=module_id,
            sandboxed=bool(res.get("sandboxed")),
            reason=("pytest did not produce a parsable pass/fail summary"
                    if not summary_found else "pytest exited unsuccessfully"),
            mode="pytest", returncode=res.get("returncode"), output=output[-1000:],
        )

    res = await run_in_sandbox(workspace, _IMPORT_SMOKE_SCRIPT, timeout=90.0)
    if not res.get("sandboxed"):
        return _result(
            verification="unverified", total=0, passed=0, failed=0,
            module_id=module_id, sandboxed=False,
            reason="Docker was reachable but the import-smoke worker container did not start",
            mode="import-smoke", returncode=res.get("returncode"),
            output=f"{res.get('stdout', '')}\n{res.get('stderr', '')}"[-1000:],
        )
    ok = bool(res.get("sandboxed")) and res.get("returncode") == 0
    if ok:
        return _result(
            verification="unverified", total=0, passed=0, failed=0,
            module_id=module_id, sandboxed=True,
            reason="imports load, but no executable test suite was present",
            mode="import-smoke",
        )
    return _result(
        verification="failed", total=len(py_files), passed=0, failed=len(py_files),
        module_id=module_id, sandboxed=bool(res.get("sandboxed")),
        reason="container import smoke failed", mode="import-smoke",
        returncode=res.get("returncode"),
        output=f"{res.get('stdout', '')}\n{res.get('stderr', '')}"[-1000:],
    )
