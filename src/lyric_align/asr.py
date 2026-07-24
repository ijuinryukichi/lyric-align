"""ASR backend: faster-whisper (optional dependency).

Kept behind a lazy import so the core aligner has zero heavy dependencies. If
you already have segments (from any Whisper flavor), skip this and feed the
aligner directly via `Segment.from_dict`.
"""
from __future__ import annotations

from pathlib import Path

from .model import Segment, Word


def transcribe(
    audio_path: str | Path,
    *,
    language: str = "ja",
    model_size: str = "medium",
    device: str = "cpu",
    compute_type: str = "int8",
    vad: bool = True,
) -> list[Segment]:
    """Transcribe with faster-whisper, returning word-timed segments.

    Requires the `[asr]` extra: pip install lyric-align[asr]
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "faster-whisper is required for transcription. "
            "Install with: pip install lyric-align[asr]"
        ) from e

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    kwargs = dict(language=language, word_timestamps=True)
    if vad:
        kwargs.update(vad_filter=True,
                      vad_parameters=dict(min_silence_duration_ms=500))
    segments, _ = model.transcribe(str(audio_path), **kwargs)

    out = []
    for seg in segments:
        words = [Word(float(w.start), float(w.end), w.word)
                 for w in (seg.words or [])]
        out.append(Segment(float(seg.start), float(seg.end), seg.text.strip(), words))
    return out
