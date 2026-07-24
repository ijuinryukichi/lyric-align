"""Map known characters to sung times by proportional interpolation.

Given the ASR word boundaries for a line and the *known* character string, we
distribute the characters proportionally across the word-time span. This lets
karaoke output use the correct lyric text while borrowing only the timing from
the (possibly misspelled) ASR words.
"""
from __future__ import annotations

from .model import Word
from .normalize import nchars


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
