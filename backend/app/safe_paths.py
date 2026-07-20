"""Cross-platform containment for untrusted relative paths."""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

_WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


class UnsafePathError(ValueError):
    """Raised when an untrusted path cannot be proven to stay inside its base."""


def resolve_within(base: str | Path, relative: str | Path) -> Path:
    """Resolve an untrusted relative path below *base*, or fail closed.

    Both POSIX and Windows path syntax are validated so a value rejected on one
    deployment cannot become an escape after the package moves to another OS.
    Backslashes in otherwise-relative paths are treated as directory separators.
    """
    if not isinstance(relative, (str, Path)):
        raise UnsafePathError("path must be a string or Path")

    raw = str(relative)
    if not raw or not raw.strip() or "\x00" in raw:
        raise UnsafePathError("path must be a non-empty relative path")

    windows_path = PureWindowsPath(raw)
    if windows_path.drive or windows_path.root or raw.startswith(("//", "\\\\")):
        raise UnsafePathError("absolute, drive, and UNC paths are not allowed")

    portable = PurePosixPath(raw.replace("\\", "/"))
    if portable.is_absolute() or not portable.parts:
        raise UnsafePathError("path must be relative")
    if any(part == ".." for part in portable.parts):
        raise UnsafePathError("parent path components are not allowed")
    for part in portable.parts:
        if ":" in part:
            raise UnsafePathError("NTFS alternate-data-stream paths are not allowed")
        if part.endswith((" ", ".")):
            raise UnsafePathError("path components may not end with a dot or space")
        device_stem = part.split(".", 1)[0].rstrip(" .").upper()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            raise UnsafePathError("Windows reserved device names are not allowed")

    try:
        root = Path(base).resolve(strict=False)
        candidate = (root / Path(*portable.parts)).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, ValueError) as exc:
        raise UnsafePathError("path escapes its allowed base") from exc

    if candidate == root:
        raise UnsafePathError("path must identify an entry below its base")
    return candidate
