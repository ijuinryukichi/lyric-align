"""Split a merged ASR segment back into individual lyric lines.

ASR (Whisper etc.) tends to merge several sung lines into one segment. When we
know how many lines a segment should contain, we can recover per-line
boundaries by cutting at the largest inter-word time gap (a breath) near the
expected split point — estimated from the character-count ratio of the known
lines.
"""
from __future__ import annotations

from .model import Word
from .normalize import nchars


def split_words_by_breath(words: list[Word], lines: list[str],
                          search: int = 3) -> list[list[Word]]:
    """Partition `words` into len(lines) groups.

    For each split point, aim at the index implied by cumulative character
    ratio of `lines`, then within ±`search` words pick the boundary with the
    largest silence gap (the breath). Returns one word-list per line; groups
    may be empty if there are fewer words than lines.
    """
    n = len(words)
    if not lines:
        return []
    if len(lines) == 1 or n <= 1:
        return [words] + [[] for _ in lines[1:]]

    total_chars = sum(nchars(l) for l in lines) or 1
    groups: list[list[Word]] = []
    start = 0
    cum_chars = 0
    for li, line in enumerate(lines[:-1]):
        cum_chars += nchars(line)
        # words remaining must cover the remaining lines (>=1 each)
        remaining_lines = len(lines) - li - 1
        target = round(n * cum_chars / total_chars)
        lo = max(start + 1, target - search)
        hi = min(n - remaining_lines, target + search + 1)
        if hi <= lo:
            cut = min(max(lo, start + 1), n - remaining_lines)
        else:
            best_gap, cut = -1.0, lo
            for i in range(lo, hi):
                gap = words[i].start - words[i - 1].end
                if gap > best_gap:
                    best_gap, cut = gap, i
        groups.append(words[start:cut])
        start = cut
    groups.append(words[start:])
    return groups
