"""Map known characters to sung times by proportional interpolation.

Given the ASR word boundaries for a line and the *known* character string, we
distribute the characters proportionally across the word-time span. This lets
karaoke output use the correct lyric text while borrowing only the timing from
the (possibly misspelled) ASR words.
"""
from __future__ import annotations

from .model import Word
from .normalize import cjk_ratio, nchars


def char_timings(text: str, words: list[Word]) -> list[dict]:
    """Return [{"char", "start", "end"}] for each non-space character in text.

    Spaces are skipped (no karaoke syllable). If `words` is empty, returns [].
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

    out = []
    j = 0
    for ch in text:
        if ch == ' ':
            continue
        out.append({"char": ch, "start": round(t_at(j), 3),
                    "end": round(t_at(j + 1), 3)})
        j += 1
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
