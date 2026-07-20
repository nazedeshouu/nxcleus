"""Regression coverage for untrusted package, workspace, and tool paths."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import processes
from app.config import settings
from app.orchestrator import codeexec, toolsmith
from app.runtime import workspace
from app.safe_paths import UnsafePathError, resolve_within


@pytest.mark.parametrize("relative", [
    "",
    "   ",
    ".",
    "../secret.py",
    r"..\secret.py",
    "/etc/passwd",
    r"C:\temp\secret.py",
    r"C:relative.py",
    r"\\server\share\secret.py",
    "//server/share/secret.py",
])
def test_resolve_within_rejects_cross_platform_escapes(tmp_path, relative):
    with pytest.raises(UnsafePathError):
        resolve_within(tmp_path / "base", relative)


@pytest.mark.parametrize("relative", [
    "CON",
    "con.txt",
    "PRN.",
    "aux ",
    "src/NUL.json",
    "src/COM1.py",
    "src/lpt9.log",
    "src/file.py:secret",
    r"src\normal.py:$DATA",
])
def test_resolve_within_rejects_windows_devices_and_ntfs_streams(tmp_path, relative):
    with pytest.raises(UnsafePathError):
        resolve_within(tmp_path / "base", relative)


def test_resolve_within_accepts_nested_portable_paths(tmp_path):
    base = tmp_path / "base"
    assert resolve_within(base, "src/pkg/module.py") == (base / "src/pkg/module.py").resolve()
    assert resolve_within(base, r"src\pkg\module.py") == (base / "src/pkg/module.py").resolve()
    for portable_name in ("console.py", "com10.py", "lpt0.py"):
        assert resolve_within(base, portable_name) == (base / portable_name).resolve()


def test_resolve_within_rejects_symlink_escape(tmp_path):
    base = tmp_path / "base"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    link = base / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")

    with pytest.raises(UnsafePathError):
        resolve_within(base, "linked/secret.py")


def test_workspace_writes_utf8_but_cannot_replace_shared_interfaces(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    job_id = "job-path-safety"
    workspace.write_shared_interfaces(job_id, [{"name": "trusted"}])
    shared = workspace.job_dir(job_id) / "shared" / "interfaces.json"
    original = shared.read_bytes()

    written = workspace.write_files(job_id, [
        {"path": "src/nested/module.py", "content": '# café\nVALUE = "✓"\n'},
    ])
    generated = workspace.job_dir(job_id) / "src" / "nested" / "module.py"
    assert written == ["src/nested/module.py"]
    assert generated.read_text(encoding="utf-8").endswith('VALUE = "✓"\n')
    assert b"caf\xc3\xa9" in generated.read_bytes()

    with pytest.raises(UnsafePathError):
        workspace.write_files(job_id, [
            {"path": "shared/interfaces.json", "content": "attacker controlled"},
        ])
    assert shared.read_bytes() == original


def _assemble(*, slug: str, src_files: list[dict]) -> Path:
    return Path(workspace.assemble_package(
        slug=slug,
        version=1,
        manifest={"trusted": True},
        plan={},
        amendments=[],
        consults=[],
        goal={},
        src_files=src_files,
        tests=[],
        vectors=[],
        docs={},
        invoice={"trusted": True},
    ))


def test_assemble_package_contains_sources_and_protects_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    root = _assemble(slug="valid-process", src_files=[
        {"path": "src/pkg/module.py", "content": "VALUE = 'данные'\n"},
        {"path": "process.py", "content": "def run_unit(unit): return unit\n"},
    ])
    assert (root / "src/pkg/module.py").read_text(encoding="utf-8").endswith("'данные'\n")
    assert json.loads((root / "manifest.json").read_text(encoding="utf-8")) == {"trusted": True}

    with pytest.raises(UnsafePathError):
        _assemble(slug="protected-process", src_files=[
            {"path": "src/valid.py", "content": "VALUE = 1\n"},
            {"path": "manifest.json", "content": '{"trusted": false}'},
        ])
    protected = settings.packages_dir / "protected-process" / "1"
    assert not protected.exists()

    with pytest.raises(UnsafePathError, match="duplicate"):
        _assemble(slug="duplicate-process", src_files=[
            {"path": "src/pkg/module.py", "content": "VALUE = 1\n"},
            {"path": "src/PKG/MODULE.py", "content": "VALUE = 2\n"},
        ])
    assert not (settings.packages_dir / "duplicate-process" / "1").exists()

    with pytest.raises(UnsafePathError):
        _assemble(slug="../escaped", src_files=[])


async def test_package_endpoint_serves_contained_file_and_hides_traversal(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    normal = package / "docs" / "README.md"
    normal.parent.mkdir()
    normal.write_text("safe", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    async def fake_version(process_id: str, version: int):
        return {"package_path": str(package)}

    monkeypatch.setattr(processes.dao, "get_version", fake_version)
    response = await processes.package_file("process-1", 1, "docs/README.md")
    assert Path(response.path) == normal.resolve()

    for attack in ("../secret.txt", r"..\secret.txt", str(outside), r"C:\secret.txt"):
        with pytest.raises(HTTPException) as caught:
            await processes.package_file("process-1", 1, attack)
        assert caught.value.status_code == 404
        assert caught.value.detail["error"]["message"] == "file not found"


@pytest.mark.parametrize("model_name", ["../../escape", "con"])
async def test_toolsmith_rejects_malicious_model_filename_before_writing(
        tmp_path, monkeypatch, model_name):
    source = f"""\
TOOL = {{"name": {model_name!r}, "description": "bad", "args_schema": {{}}}}
SELF_TEST = {{"args": {{}}, "expect_keys": []}}
def run(args):
    return {{}}
"""
    calls = {"complete": 0, "sandbox": 0}

    async def malicious_complete(*args, **kwargs):
        calls["complete"] += 1
        return SimpleNamespace(parsed={"file": source})

    async def sandbox_must_not_run(*args, **kwargs):
        calls["sandbox"] += 1
        raise AssertionError("malicious tool must be rejected before sandbox execution")

    monkeypatch.setattr(codeexec, "docker_available", lambda: True)
    monkeypatch.setattr(codeexec, "run_in_sandbox", sandbox_must_not_run)
    result = await toolsmith.create_tool(
        purpose="malicious fixture",
        args_example={},
        scope="job:path-safety",
        complete_fn=malicious_complete,
        agent_dir=tmp_path / "agent",
    )

    assert "contract parse failed" in result["error"]
    assert calls == {"complete": 2, "sandbox": 0}
    assert not (tmp_path / "escape.py").exists()
    assert not (tmp_path / "agent" / "tools").exists()


@pytest.mark.parametrize("name", ["../tool", "BadTool", "two__underscores", "class"])
def test_toolsmith_name_must_be_strict_snake_case(name):
    source = f"""\
TOOL = {{"name": {name!r}, "description": "bad", "args_schema": {{}}}}
SELF_TEST = {{"args": {{}}, "expect_keys": []}}
def run(args):
    return {{}}
"""
    with pytest.raises(ValueError, match="snake_case"):
        toolsmith._parse_tool_file(source)


@pytest.mark.parametrize("name", ["con", "prn", "aux", "nul", "com1", "lpt9"])
def test_toolsmith_name_cannot_be_a_windows_device(name):
    source = f"""\
TOOL = {{"name": {name!r}, "description": "bad", "args_schema": {{}}}}
SELF_TEST = {{"args": {{}}, "expect_keys": []}}
def run(args):
    return {{}}
"""
    with pytest.raises(ValueError, match="portable filename"):
        toolsmith._parse_tool_file(source)


def test_toolsmith_name_has_a_bounded_length():
    name = "a" * 65
    source = f"""\
TOOL = {{"name": {name!r}, "description": "bad", "args_schema": {{}}}}
SELF_TEST = {{"args": {{}}, "expect_keys": []}}
def run(args):
    return {{}}
"""
    with pytest.raises(ValueError, match="at most 64"):
        toolsmith._parse_tool_file(source)
