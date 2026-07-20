from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
import types

import pytest

from app.orchestrator import codeexec


@pytest.mark.asyncio
async def test_valid_workspace_without_docker_is_unverified(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "process.py").write_text(
        "def run_unit(unit):\n    return unit\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: False)

    result = await codeexec.run_tests(workspace=str(workspace), tests=[{"id": "T-1"}])

    assert result["verification"] == "unverified"
    assert result["passed"] == result["failed"] == 0
    assert result["sandboxed"] is False


@pytest.mark.asyncio
async def test_outside_workspace_is_failed_even_without_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(codeexec.settings, "data_dir", str(tmp_path / "trusted-data"))
    _ = codeexec.settings.workspaces_dir
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "process.py").write_text("VALUE = 1\n", encoding="utf-8")
    docker_calls = {"count": 0}

    def unavailable():
        docker_calls["count"] += 1
        return False

    monkeypatch.setattr(codeexec, "docker_available", unavailable)
    result = await codeexec.run_tests(workspace=str(outside), tests=[])

    assert result["verification"] == "failed"
    assert result["mode"] == "workspace-validation"
    assert result["failed"] == 1
    assert docker_calls["count"] == 0


@pytest.mark.asyncio
async def test_static_parse_includes_root_process_when_src_exists(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "src").mkdir()
    (workspace / "src" / "valid.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "process.py").write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: False)

    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "failed"
    assert result["mode"] == "static-parse"
    assert result["static_errors"][0]["path"] == "process.py"


@pytest.mark.asyncio
async def test_pytest_launch_without_summary_is_failed(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_generated.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def failed_launch(*_args, **_kwargs):
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "python: No module named pytest",
            "sandboxed": True,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", failed_launch)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[{"id": "T-1"}])

    assert result["verification"] == "failed"
    assert result["failed"] == 1
    assert "parsable" in result["reason"]


@pytest.mark.asyncio
async def test_pytest_container_not_started_is_unverified(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_generated.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def missing_image(*_args, **_kwargs):
        return {
            "returncode": 125,
            "stdout": "",
            "stderr": "No such image: nxcleus/codeexec:py312",
            "sandboxed": False,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", missing_image)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[{"id": "T-1"}])

    assert result["verification"] == "unverified"
    assert result["passed"] == result["failed"] == 0
    assert result["sandboxed"] is False
    assert "did not start" in result["reason"]


@pytest.mark.asyncio
async def test_import_smoke_container_not_started_is_unverified(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "process.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def cli_launch_failure(*_args, **_kwargs):
        return {
            "returncode": 126,
            "stdout": "",
            "stderr": "docker launch failed",
            "sandboxed": False,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", cli_launch_failure)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "unverified"
    assert result["passed"] == result["failed"] == 0
    assert result["sandboxed"] is False
    assert "did not start" in result["reason"]


@pytest.mark.asyncio
async def test_import_smoke_fails_on_syntactically_valid_missing_import(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "process.py").write_text(
        "from _fake import run\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def missing_import(_workspace, script, **_kwargs):
        assert "importlib.import_module" in script
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "ModuleNotFoundError: No module named '_fake'",
            "sandboxed": True,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", missing_import)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "failed"
    assert result["mode"] == "import-smoke"
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_import_smoke_loads_valid_package_but_remains_unverified(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "src").mkdir()
    (workspace / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "process.py").write_text(
        "from src.module import VALUE\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def imports_ok(_workspace, script, **_kwargs):
        assert "importlib.import_module" in script
        assert "sys.path.insert" in script
        return {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "sandboxed": True,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", imports_ok)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "unverified"
    assert result["mode"] == "import-smoke"
    assert result["passed"] == result["failed"] == 0
    assert result["sandboxed"] is True
    assert "no executable test suite" in result["reason"]


@pytest.mark.asyncio
async def test_import_smoke_ignores_non_deliverable_agent_modules(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    (workspace / "process.py").write_text("VALUE = 1\n", encoding="utf-8")
    agent_dir = workspace / "agents" / "sanitized-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "invalid-module-name.py").write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "docker_available", lambda: True)

    async def deliverable_imports_ok(_workspace, script, **_kwargs):
        assert 'entrypoint = root / "process.py"' in script
        assert 'src = root / "src"' in script
        assert "root.rglob" not in script
        return {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "sandboxed": True,
            "timed_out": False,
        }

    monkeypatch.setattr(codeexec, "run_in_sandbox", deliverable_imports_ok)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "unverified"
    assert result["passed"] == result["failed"] == 0


def test_docker_available_probes_daemon_with_bounded_timeout(monkeypatch):
    seen = {}
    codeexec._reset_docker_availability_cache()
    monkeypatch.setattr(codeexec.shutil, "which", lambda _name: "C:/docker.exe")

    def probe(*args, **kwargs):
        seen["args"] = args
        seen["timeout"] = kwargs["timeout"]
        return types.SimpleNamespace(returncode=0, stdout="27.0.0\n")

    monkeypatch.setattr(codeexec.subprocess, "run", probe)
    assert codeexec.docker_available() is True
    assert seen["args"][0][:2] == ["docker", "info"]
    assert 0 < seen["timeout"] <= 5

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("docker", 3)

    codeexec._reset_docker_availability_cache()
    monkeypatch.setattr(codeexec.subprocess, "run", timeout)
    assert codeexec.docker_available() is False
    codeexec._reset_docker_availability_cache()


def test_docker_availability_result_has_short_ttl_cache(monkeypatch):
    calls = {"count": 0}

    def probe():
        calls["count"] += 1
        return True

    codeexec._reset_docker_availability_cache()
    monkeypatch.setattr(codeexec, "_probe_docker", probe)
    assert codeexec.docker_available() is True
    assert codeexec.docker_available() is True
    assert calls["count"] == 1
    codeexec._reset_docker_availability_cache()


@pytest.mark.asyncio
async def test_async_docker_probe_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_probe():
        started.set()
        release.wait(timeout=1)
        return False

    monkeypatch.setattr(codeexec, "docker_available", slow_probe)
    task = asyncio.create_task(codeexec.docker_available_async())
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)

    assert started.is_set() and not task.done()
    release.set()
    assert await task is False


class _FinishedProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    async def communicate(self):
        return self.stdout, self.stderr

    async def wait(self):
        return self.returncode


class _HangingProcess:
    def __init__(self):
        self.returncode = None
        self.killed = False
        self.started = asyncio.Event()

    async def communicate(self):
        self.started.set()
        await asyncio.Event().wait()

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


class _TimeoutProcess(_HangingProcess):
    async def communicate(self):
        raise TimeoutError


async def _available():
    return True


def _local_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(codeexec.settings, "data_dir", str(tmp_path))
    workspace = tmp_path / "workspaces" / "job-codeexec"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(codeexec, "_running_in_container", lambda: False)
    return workspace


@pytest.mark.asyncio
async def test_inspect_timeout_kills_and_reaps_cli(monkeypatch):
    process = _TimeoutProcess()

    async def create_process(*_args, **_kwargs):
        return process

    codeexec._host_data_source_cache.clear()
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    source, error = await codeexec._inspect_host_data_source("api-timeout", "/data")

    assert source is None and "TimeoutError" in error
    assert process.killed is True


@pytest.mark.asyncio
async def test_inspect_cancellation_kills_and_reaps_cli(monkeypatch):
    process = _HangingProcess()

    async def create_process(*_args, **_kwargs):
        return process

    codeexec._host_data_source_cache.clear()
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(codeexec._inspect_host_data_source("api-cancel", "/data"))
    await process.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True


@pytest.mark.asyncio
async def test_containerized_workspace_translates_to_exact_host_volume_subdir(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(codeexec.settings, "data_dir", str(tmp_path))
    workspace = tmp_path / "workspaces" / "job-a" / "agents" / "Mod_A"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(codeexec, "_running_in_container", lambda: True)

    async def inspect(container_id, destination):
        assert container_id
        assert destination == str(tmp_path.resolve())
        return "/var/lib/docker/volumes/vm_platform-data/_data", None

    monkeypatch.setattr(codeexec, "_inspect_host_data_source", inspect)
    trusted, error = codeexec._trusted_workspace(str(workspace))
    assert error is None and trusted is not None
    args, error = await codeexec._workspace_mount_args(trusted)

    assert error is None
    assert args == [
        "--mount",
        "type=bind,src=/var/lib/docker/volumes/vm_platform-data/_data/"
        "workspaces/job-a/agents/Mod_A,dst=/src,readonly",
    ]


def test_workspace_containment_rejects_outside_and_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(codeexec.settings, "data_dir", str(tmp_path / "data"))
    trusted_root = codeexec.settings.workspaces_dir
    (trusted_root / "job-a").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    traversal_target = trusted_root.parent / "outside"
    traversal_target.mkdir()

    for candidate in (outside, trusted_root / "job-a" / ".." / ".." / "outside"):
        resolved, error = codeexec._trusted_workspace(str(candidate))
        assert resolved is None
        assert "outside the trusted workspace root" in error


@pytest.mark.asyncio
async def test_local_workspace_uses_exact_direct_bind(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    trusted, error = codeexec._trusted_workspace(str(workspace))
    assert error is None and trusted is not None

    args, error = await codeexec._workspace_mount_args(trusted)

    assert error is None
    assert args == ["--mount", f"type=bind,src={trusted},dst=/src,readonly"]


@pytest.mark.parametrize("unsafe", ["/tmp/job,other", "/tmp/job\rname", "/tmp/job\nname"])
def test_local_bind_rejects_mount_delimiters(unsafe):
    args, error = codeexec._bind_mount_args(unsafe)

    assert args is None
    assert "not safe" in error


@pytest.mark.asyncio
@pytest.mark.parametrize("inspect_error", [
    "trusted data mount is missing",
    "trusted data mount is ambiguous",
])
async def test_container_mount_mapping_failure_is_unverified(
    monkeypatch, tmp_path, inspect_error,
):
    monkeypatch.setattr(codeexec.settings, "data_dir", str(tmp_path))
    workspace = tmp_path / "workspaces" / "job-a"
    workspace.mkdir(parents=True)
    (workspace / "process.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(codeexec, "_running_in_container", lambda: True)
    monkeypatch.setattr(codeexec, "docker_available_async", _available)

    async def inspect(*_args):
        return None, inspect_error

    monkeypatch.setattr(codeexec, "_inspect_host_data_source", inspect)
    result = await codeexec.run_tests(workspace=str(workspace), tests=[])

    assert result["verification"] == "unverified"
    assert result["sandboxed"] is False
    assert result["passed"] == result["failed"] == 0
    assert inspect_error in result["output"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mounts", [
    [],
    [
        {"Destination": "/data", "Source": "/host/one"},
        {"Destination": "/data", "Source": "/host/two"},
    ],
])
async def test_self_inspect_rejects_missing_or_ambiguous_data_mount(monkeypatch, mounts):
    payload = json.dumps([{"Mounts": mounts}]).encode()

    async def create_process(*_args, **_kwargs):
        return _FinishedProcess(stdout=payload)

    codeexec._host_data_source_cache.clear()
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    source, error = await codeexec._inspect_host_data_source("api-container", "/data")

    assert source is None
    assert "missing or ambiguous" in error


@pytest.mark.asyncio
async def test_sandbox_arguments_are_hardened_and_names_are_unique(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    calls = []

    async def create_process(*args, **_kwargs):
        calls.append(args)
        return _FinishedProcess()

    monkeypatch.setattr(codeexec, "docker_available_async", _available)
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    await codeexec.run_in_sandbox(str(workspace), "python -V")
    await codeexec.run_in_sandbox(str(workspace), "python -V")

    names = []
    for command in calls:
        assert command[:4] == ("docker", "run", "--rm", "--pull=never")
        name = command[command.index("--name") + 1]
        names.append(name)
        assert re.fullmatch(r"nxcleus-codeexec-[0-9a-f]{32}", name)
        assert command[command.index("--cap-drop") + 1] == "ALL"
        assert command[command.index("--security-opt") + 1] == "no-new-privileges:true"
        assert command[command.index("--user") + 1] == "65532:65532"
        tmpfs = command[command.index("--tmpfs") + 1]
        assert "noexec" in tmpfs and "uid=65532" in tmpfs and "mode=0700" in tmpfs
        assert "cp -R /src/. /work/" in command[-1]
    assert names[0] != names[1]


@pytest.mark.asyncio
async def test_timeout_kills_cli_and_force_removes_named_container(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    running = _HangingProcess()
    calls = []

    async def create_process(*args, **_kwargs):
        calls.append(args)
        return _FinishedProcess() if args[:3] == ("docker", "rm", "-f") else running

    monkeypatch.setattr(codeexec, "docker_available_async", _available)
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    result = await codeexec.run_in_sandbox(str(workspace), "python -V", timeout=0.001)

    container_name = calls[0][calls[0].index("--name") + 1]
    assert running.killed is True
    assert calls[1] == ("docker", "rm", "-f", container_name)
    assert result["timed_out"] is True and result["sandboxed"] is True


@pytest.mark.asyncio
async def test_cancellation_force_removes_named_container(monkeypatch, tmp_path):
    workspace = _local_workspace(monkeypatch, tmp_path)
    running = _HangingProcess()
    calls = []

    async def create_process(*args, **_kwargs):
        calls.append(args)
        return _FinishedProcess() if args[:3] == ("docker", "rm", "-f") else running

    monkeypatch.setattr(codeexec, "docker_available_async", _available)
    monkeypatch.setattr(codeexec.asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(codeexec.run_in_sandbox(str(workspace), "python -V"))
    await running.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    container_name = calls[0][calls[0].index("--name") + 1]
    assert running.killed is True
    assert calls[1] == ("docker", "rm", "-f", container_name)


def test_unverified_delivery_override_is_mock_only(monkeypatch):
    assert codeexec.settings.__class__.model_fields["allow_unverified_demo_delivery"].default is False
    monkeypatch.setattr(codeexec.settings, "allow_unverified_demo_delivery", True)
    monkeypatch.setattr(codeexec.settings, "model_mode", "live")
    assert codeexec.unverified_demo_delivery_allowed() is False
    assert codeexec.settings.safe_summary()["allow_unverified_demo_delivery"] is False

    monkeypatch.setattr(codeexec.settings, "model_mode", "mock")
    assert codeexec.unverified_demo_delivery_allowed() is True
    assert codeexec.settings.safe_summary()["allow_unverified_demo_delivery"] is True
