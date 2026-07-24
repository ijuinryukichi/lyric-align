"""Output formatters: JSON, LRC, SRT, and karaoke ASS."""
from __future__ import annotations

import json

from .model import AlignedLine


def _skip(a: AlignedLine) -> bool:
    return a.start is None or a.end is None


def to_json(aligned: list[AlignedLine]) -> str:
    return json.dumps([a.to_dict() for a in aligned], ensure_ascii=False, indent=1)


def _lrc_ts(t: float) -> str:
    m = int(t // 60)
    s = t - m * 60
    return f"[{m:02d}:{s:05.2f}]"


def to_lrc(aligned: list[AlignedLine]) -> str:
    lines = []
    for a in aligned:
        if _skip(a):
            continue
        lines.append(f"{_lrc_ts(a.start)}{a.line}")
    return "\n".join(lines) + "\n"


def _srt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(aligned: list[AlignedLine]) -> str:
    out = []
    n = 1
    for a in aligned:
        if _skip(a):
            continue
        out.append(str(n))
        out.append(f"{_srt_ts(a.start)} --> {_srt_ts(a.end)}")
        out.append(a.line)
        out.append("")
        n += 1
    return "\n".join(out)


def _ass_ts(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Sans,64,&H00FFFFFF,&H00888888,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def to_ass(aligned: list[AlignedLine], karaoke: bool = False) -> str:
    """Standard ASS subtitle. If karaoke and per-char timings exist, emit \\k
    tags so the line highlights syllable-by-syllable."""
    body = []
    for a in aligned:
        if _skip(a):
            continue
        if karaoke and a.chars:
            parts = []
            for c in a.chars:
                cs = max(0, int(round((c["end"] - c["start"]) * 100)))
                parts.append(f"{{\\k{cs}}}{c['char']}")
            text = "".join(parts)
        else:
            text = a.line
        body.append(f"Dialogue: 0,{_ass_ts(a.start)},{_ass_ts(a.end)},Default,,0,0,0,,{text}")
    return ASS_HEADER + "\n".join(body) + "\n"


FORMATTERS = {
    "json": lambda a, karaoke=False: to_json(a),
    "lrc": lambda a, karaoke=False: to_lrc(a),
    "srt": lambda a, karaoke=False: to_srt(a),
    "ass": lambda a, karaoke=False: to_ass(a, karaoke=karaoke),
}
