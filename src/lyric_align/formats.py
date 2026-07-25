"""Output formatters.

Each format exists because some downstream tool eats it:

- ``lrc``  — the de-facto lyrics format; music players and the LRCLIB database.
- ``elrc`` — LRC A2 / Enhanced LRC, the same file with inline per-word timestamps;
  word-level players (AIMP, QQ/NetEase/Kugou, Chronograph) and karaoke editors.
- ``srt``  — universal subtitles: ffmpeg, video editors, YouTube captions.
- ``vtt``  — WebVTT, for HTML5 ``<track>`` and web players.
- ``ass``  — full styling plus ``\\k`` karaoke sweeps; Aegisub and ffmpeg burn-in.
- ``ttml`` — word-level rich lyrics (Apple-style / AMLL ecosystem).
- ``aud``  — Audacity label track, i.e. the *correction* loop: import over the
  waveform, drag the wrong lines, export. Doubles as a generic TSV.
- ``json`` — everything, including similarity scores and unmatched lines.

LRC and eLRC cannot express an end time; SRT/VTT/ASS/TTML/AUD/JSON all carry the
ones this aligner computes.
"""
from __future__ import annotations

import json
from xml.sax.saxutils import escape

from .charmap import syllable_timings
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


def to_elrc(aligned: list[AlignedLine]) -> str:
    """LRC A2 (Enhanced LRC): line timestamp plus inline per-syllable timestamps.

    Falls back to the bare line when per-character timings are absent, which keeps
    the file valid plain LRC rather than emitting something half-timed.
    """
    lines = []
    for a in aligned:
        if _skip(a):
            continue
        units = syllable_timings(a.line, a.chars or [])
        if not units:
            lines.append(f"{_lrc_ts(a.start)}{a.line}")
            continue
        body = "".join(f"<{_lrc_ts(u['start'])[1:-1]}>{u['text']}{_gap(units, i)}"
                       for i, u in enumerate(units))
        lines.append(f"{_lrc_ts(a.start)}{body}")
    return "\n".join(lines) + "\n"


def _gap(units: list[dict], i: int) -> str:
    """The separator that followed unit ``i`` in the source line.

    Taken from the line itself rather than guessed from the script, so both
    "Amazing grace" and "硫黄が満ちる 道の奥" rebuild character-for-character.
    A trailing space is dropped: lyric lines are stripped, and TTML consumers
    trim it anyway.
    """
    return " " if units[i].get("space_after") and i < len(units) - 1 else ""


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


def to_vtt(aligned: list[AlignedLine]) -> str:
    """WebVTT — same cues as SRT with dotted milliseconds, for HTML5 <track>."""
    out = ["WEBVTT", ""]
    n = 1
    for a in aligned:
        if _skip(a):
            continue
        out.append(str(n))
        out.append(f"{_srt_ts(a.start).replace(',', '.')} --> "
                   f"{_srt_ts(a.end).replace(',', '.')}")
        out.append(a.line)
        out.append("")
        n += 1
    return "\n".join(out)


def to_aud(aligned: list[AlignedLine]) -> str:
    """Audacity label track: start<TAB>end<TAB>text.

    The point of this format is the round trip. Audacity's File > Import > Labels
    puts every line on the waveform, where a wrong hook placement is obvious and
    can be dragged into place, then exported again. Also readable as plain TSV.
    """
    rows = []
    for a in aligned:
        if _skip(a):
            continue
        rows.append(f"{a.start:.6f}\t{a.end:.6f}\t{a.line}")
    return "\n".join(rows) + "\n"


def _ttml_ts(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def to_ttml(aligned: list[AlignedLine], lang: str = "") -> str:
    """TTML with per-syllable spans — the shape Apple-style rich lyrics use.

    Word timings become nested <span> elements inside the line <p>, which is what
    players in that ecosystem (e.g. AMLL) read for word-by-word highlighting.

    Verified against the AMLL reference parser (``@applemusic-like-lyrics/ttml``):
    lines, per-unit text and millisecond timings survive a real parse, and the
    spaces between units are emitted as text nodes outside the spans, which is
    the separator form that specification calls most compliant.

    Only the metadata we actually know is written. A single ``ttm:agent`` is
    declared and referenced because the spec requires one per line; the title,
    artist and album an AMLL database submission also wants are left out rather
    than invented, since this tool is given audio and lyrics and nothing else.
    """
    body = []
    word_level = False
    for i, a in enumerate(aligned, 1):
        if _skip(a):
            continue
        units = syllable_timings(a.line, a.chars or [])
        p_open = (f'      <p begin="{_ttml_ts(a.start)}" end="{_ttml_ts(a.end)}" '
                  f'itunes:key="L{i}" ttm:agent="v1">')
        if units:
            word_level = True
            inner = "".join(
                f'<span begin="{_ttml_ts(u["start"])}" end="{_ttml_ts(u["end"])}">'
                f'{escape(u["text"])}</span>{_gap(units, j)}'
                for j, u in enumerate(units))
        else:
            inner = escape(a.line)
        body.append(f"{p_open}{inner}</p>")
    lang_attr = f'\n    xml:lang="{escape(lang)}"' if lang else ""
    timing = "Word" if word_level else "Line"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<tt xmlns="http://www.w3.org/ns/ttml"\n'
        '    xmlns:ttm="http://www.w3.org/ns/ttml#metadata"\n'
        '    xmlns:itunes="http://music.apple.com/lyric-ttml-internal"'
        f'{lang_attr}\n'
        f'    itunes:timing="{timing}">\n'
        '  <head>\n'
        '    <metadata>\n'
        '      <ttm:agent type="person" xml:id="v1"/>\n'
        '    </metadata>\n'
        '  </head>\n'
        '  <body>\n'
        '    <div>\n'
        + "\n".join(body) + "\n"
        '    </div>\n'
        '  </body>\n'
        '</tt>\n'
    )


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
    "json": lambda a, karaoke=False, lang="": to_json(a),
    "lrc": lambda a, karaoke=False, lang="": to_lrc(a),
    "elrc": lambda a, karaoke=False, lang="": to_elrc(a),
    "srt": lambda a, karaoke=False, lang="": to_srt(a),
    "vtt": lambda a, karaoke=False, lang="": to_vtt(a),
    "ass": lambda a, karaoke=False, lang="": to_ass(a, karaoke=karaoke),
    "ttml": lambda a, karaoke=False, lang="": to_ttml(a, lang=lang),
    "aud": lambda a, karaoke=False, lang="": to_aud(a),
}

# Formats whose whole point is per-syllable timing, so the CLI computes character
# timings for them even without --karaoke.
NEEDS_SYLLABLES = frozenset({"elrc", "ttml"})

# Filename suffix per format when writing several at once (-f all). Audacity's
# label importer filters for .txt, so that is what the label track gets.
EXTENSIONS = {
    "json": ".json", "lrc": ".lrc", "elrc": ".elrc", "srt": ".srt",
    "vtt": ".vtt", "ass": ".ass", "ttml": ".ttml", "aud": ".labels.txt",
}
