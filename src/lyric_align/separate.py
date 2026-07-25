"""Vocal separation via Demucs (optional dependency).

Aligning against an isolated vocal stem is markedly more reliable than against a
full mix: the ASR stops transcribing the instrumental and its word timings stop
drifting onto drum hits. This module is a thin, cached wrapper — Demucs stays
behind the `[separate]` extra so the core aligner keeps zero heavy dependencies.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _pick_device() -> str:
    """Prefer an accelerator when torch exposes one; fall back to CPU."""
    try:
        import torch
    except ImportError:  # pragma: no cover - torch ships with demucs
        return "cpu"
    try:
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except AttributeError:  # pragma: no cover - older torch builds
        pass
    return "cpu"


def separate_vocals(
    audio_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    model: str = "htdemucs",
    device: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Split `audio_path` and return the path to its vocal stem.

    Requires the `[separate]` extra: pip install lyric-align[separate]

    The stem is written to `<out_dir>/<model>/<stem name>/vocals.wav` (Demucs'
    own layout) and reused on later runs unless `overwrite` is set — separation
    is by far the slowest step, so re-running a failed alignment should not pay
    for it twice.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio not found: {audio_path}")

    out_dir = Path(out_dir) if out_dir else audio_path.parent / "separated"
    vocals = out_dir / model / audio_path.stem / "vocals.wav"
    if vocals.exists() and not overwrite:
        return vocals

    if shutil.which("ffmpeg") is None and audio_path.suffix.lower() != ".wav":
        raise RuntimeError(
            f"ffmpeg is required to read {audio_path.suffix} files. "
            "Install ffmpeg, or convert the input to WAV first."
        )

    try:
        import demucs  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "demucs is required for vocal separation. "
            "Install with: pip install lyric-align[separate]"
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "-n", model,
           "--two-stems", "vocals",
           "-d", device or _pick_device(),
           "-o", str(out_dir), str(audio_path)]
    subprocess.run(cmd, check=True)

    if not vocals.exists():
        raise FileNotFoundError(
            f"Demucs finished but no vocal stem at {vocals}. "
            f"Check the output under {out_dir}."
        )
    return vocals
