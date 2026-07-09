"""Local voice transcription for policy dictation (D11, O9) — whisper.cpp on the VM CPU.

The recording and transcript never leave the box (that's the demo beat). Uses `whisper-cli`
(Homebrew) with the model at `WHISPER_MODEL_PATH`. Disabled (raises) when no model is configured.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.config import settings


class WhisperUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(settings.whisper_model_path) and shutil.which(settings.whisper_cli) is not None


async def transcribe(audio_path: str | Path) -> str:
    """Transcribe an audio file locally. English-only output (track rule) via `-l en`."""
    if not settings.whisper_model_path:
        raise WhisperUnavailable("WHISPER_MODEL_PATH unset — voice input disabled (01 §6)")
    if shutil.which(settings.whisper_cli) is None:
        raise WhisperUnavailable(f"{settings.whisper_cli!r} not on PATH — install whisper.cpp")
    proc = await asyncio.create_subprocess_exec(
        settings.whisper_cli,
        "-m", settings.whisper_model_path,
        "-f", str(audio_path),
        "-l", "en",
        "-nt",              # no timestamps
        "-otxt",            # also write <file>.txt
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise WhisperUnavailable(f"whisper-cli failed: {stderr.decode()[:400]}")
    return stdout.decode().strip()
