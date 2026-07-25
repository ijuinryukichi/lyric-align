"""Anchor known lyric lines onto ASR segments (greedy forward fuzzy match).

This is the heart of lyric-align. Given the *correct* lyrics (from an official
source) and ASR segments with word timings, we place each lyric line/stanza on
the timeline by character-level fuzzy matching, moving forward monotonically so
repeated lines (choruses) consume segments in order.

The forward `window` is load-bearing, not just an optimisation: it keeps a line
from reaching a distant segment that happens to clear the threshold. Replacing
this scan with a globally optimal monotone assignment (maximise total similarity,
optionally minus a diagonal-drift penalty) was tried and measured worse — it
places every line, but repeated hooks carry no distinguishing similarity, so the
extra placements land on the wrong repetition: mean error 0.94 s -> 1.14-1.61 s,
worst 6.4 s -> 10.6 s on a track with a 4x-repeated hook. Locality beats global
optimality here because similarity alone cannot tell repetitions apart.

Design philosophy: when a line cannot be confidently matched, we mark it
unmatched rather than inventing a timestamp. Forced aligners always emit an
answer and thus fail *silently* (e.g. drifting into the intro); we prefer honest
gaps that a human — or a later interpolation pass — can fix. The same reasoning
rejects the global matcher above: a visible gap beats a confident wrong time.
"""
from __future__ import annotations

from .breath import split_words_by_breath
from .charmap import char_timings
from .model import AlignedLine, Segment
from .normalize import default_threshold, similarity


def _stanzas(lines: list[str], pairing: int) -> list[list[str]]:
    """Group lyric lines into stanza units of size `pairing` (1 = per line)."""
    if pairing < 1:
        pairing = 1
    return [lines[i:i + pairing] for i in range(0, len(lines), pairing)]


def align(
    segments: list[Segment],
    lyrics: list[str],
    *,
    pairing: int = 2,
    threshold: float | None = None,
    window: int = 4,
    karaoke: bool = False,
) -> list[AlignedLine]:
    """Align known `lyrics` lines onto ASR `segments`.

    Args:
        pairing: lyric lines per stanza unit matched to one segment. Whisper
            merges ~2 sung lines per segment, so 2 is a good default for
            Japanese rap; use 1 if your ASR already splits per line.
        threshold: minimum character similarity to accept a match. Defaults to a
            script-aware value (see `normalize.default_threshold`).
        window: how many segments ahead to search from the current position.
        karaoke: if True, compute per-character timings (needs word timings).

    Returns one AlignedLine per input lyric line (stanzas are expanded back to
    lines via breath splitting).
    """
    if threshold is None:
        threshold = default_threshold(lyrics)

    units = _stanzas(lyrics, pairing)
    results: list[AlignedLine] = []
    idx = 0

    for unit in units:
        joined = " ".join(unit)
        best_score, best_i = 0.0, None
        upper = min(idx + window, len(segments))
        for i in range(idx, upper):
            sc = similarity(joined, segments[i].text)
            if sc > best_score:
                best_score, best_i = sc, i

        if best_i is not None and best_score > threshold:
            seg = segments[best_i]
            idx = best_i + 1
            if len(unit) == 1 or not seg.words:
                # Single line, or no word timings: use the segment span as-is.
                for k, line in enumerate(unit):
                    chars = char_timings(line, seg.words) if (karaoke and k == 0) else None
                    results.append(AlignedLine(line, seg.start, seg.end,
                                               best_score, True, chars))
            else:
                groups = split_words_by_breath(seg.words, unit)
                for line, grp in zip(unit, groups):
                    if grp:
                        chars = char_timings(line, grp) if karaoke else None
                        results.append(AlignedLine(line, grp[0].start,
                                                   grp[-1].end, best_score, True, chars))
                    else:
                        results.append(AlignedLine(line, seg.start, seg.end,
                                                   best_score, True, None))
        else:
            for line in unit:
                results.append(AlignedLine(line, None, None, best_score, False, None))

    return results


def interpolate_gaps(aligned: list[AlignedLine]) -> list[AlignedLine]:
    """Fill unmatched lines by linear interpolation between known neighbors.

    Optional convenience for callers who want a fully-populated timeline. The
    `matched` flag stays False so downstream code can still tell which lines
    were guessed.
    """
    n = len(aligned)
    for i, a in enumerate(aligned):
        if a.matched or a.start is not None:
            continue
        prev = next((aligned[j] for j in range(i - 1, -1, -1)
                     if aligned[j].start is not None), None)
        nxt = next((aligned[j] for j in range(i + 1, n)
                    if aligned[j].start is not None), None)
        if prev and nxt:
            span = (nxt.start - prev.end)
            a.start = prev.end + span * 0.33
            a.end = prev.end + span * 0.66
        elif prev:
            a.start, a.end = prev.end, prev.end + 2.0
        elif nxt:
            a.start, a.end = max(0.0, nxt.start - 2.0), nxt.start
    return aligned
