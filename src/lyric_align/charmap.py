"""Map known characters to sung times by proportional interpolation.

Given the ASR word boundaries for a line and the *known* character string, we
distribute the characters proportionally across the word-time span. This lets
karaoke output use the correct lyric text while borrowing only the timing from
the (possibly misspelled) ASR words.
"""
from __future__ import annotations

from .model import Word
from .normalize import cjk_ratio, nchars


MIN_CHAR_DUR = 0.01


def char_timings(text: str, words: list[Word]) -> list[dict]:
    """Return [{"char", "start", "end"}] for each non-space character in text.

    Spaces are skipped (no karaoke syllable). If `words` is empty, returns [].

    Durations are kept strictly positive and non-overlapping: proportional
    interpolation plus rounding to milliseconds can otherwise collapse a
    character to zero length, which downstream means a `\\k0` sweep or a TTML span
    with begin == end.
    """
    if not words:
        return []
    m = nchars(text)
    if m == 0:
        return []
    bounds = [w.start for w in words] + [words[-1].end]
    n = len(bounds) - 1

    def t_at(j: float) -> float:
        pos = j * n / m
        i = min(int(pos), n - 1)
        return bounds[i] + (bounds[i + 1] - bounds[i]) * (pos - i)

    # A very short span cannot give every character MIN_CHAR_DUR; share it out.
    span = max(bounds[-1] - bounds[0], 0.0)
    min_dur = min(MIN_CHAR_DUR, span / m) if m else 0.0

    out = []
    j = 0
    prev_end = bounds[0]
    for ch in text:
        if ch == ' ':
            continue
        start = max(t_at(j), prev_end)
        end = max(t_at(j + 1), start + min_dur)
        out.append({"char": ch, "start": round(start, 3), "end": round(end, 3)})
        prev_end = end
        j += 1

    # Rounding can re-introduce a collision at millisecond resolution.
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"]:
            b["start"] = a["end"]
        if b["end"] <= b["start"]:
            b["end"] = round(b["start"] + MIN_CHAR_DUR, 3)
    if out and out[0]["end"] <= out[0]["start"]:
        out[0]["end"] = round(out[0]["start"] + MIN_CHAR_DUR, 3)
    return out


def syllable_timings(text: str, chars: list[dict]) -> list[dict]:
    """Group per-character timings into the units a karaoke format highlights.

    Returns [{"text", "start", "end"}]. The grouping differs by script, because
    what counts as a "syllable" to highlight does:

    - Alphabetic text is grouped on whitespace, so "Amazing grace" highlights two
      words rather than twelve letters.
    - CJK text keeps one unit per character, which is how per-character karaoke
      formats (QQ/NetEase style) treat Chinese and Japanese. Japanese lyrics often
      contain spaces as phrasing, so splitting on them would give useless chunks.
    """
    if not chars:
        return []
    if cjk_ratio(text) >= 0.2:
        return [{"text": c["char"], "start": c["start"], "end": c["end"]} for c in chars]

    units: list[dict] = []
    it = iter(chars)
    current: list[dict] = []
    for ch in text:
        if ch.isspace():
            if current:
                units.append(current)
                current = []
            continue
        try:
            current.append(next(it))
        except StopIteration:
            break
    if current:
        units.append(current)

    out = []
    pos = 0
    for group in units:
        # Recover the original spelling: the char timings hold only the
        # characters, so slice the source text by the same non-space run.
        while pos < len(text) and text[pos].isspace():
            pos += 1
        word = text[pos:pos + len(group)]
        pos += len(group)
        out.append({"text": word, "start": group[0]["start"], "end": group[-1]["end"]})
    return out
