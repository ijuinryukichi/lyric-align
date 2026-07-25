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

A timing prior — score candidates by `similarity - lam * |start - predicted|`,
predicting from the last placement plus the running median gap — was the obvious
next move and also measured worse (mean 0.94 s -> 1.67 s at lam=0.1, worst
6.4 s -> 10.6 s, collapsing to 8/33 placements by lam=0.5). It predicts from
*our own* previous placements, so it cannot correct a bad one; it anchors on it
and drags the following lines along. Songs do not run at one pace either, so a
median gap mispredicts hardest across a section boundary — where repeated hooks
live. Restricted to breaking near-ties it stops hurting without clearly helping
(one line gained, below the ground truth's own resolution), so it is not here.
See the README for the full sweep.

Four further attempts to fix the remaining outlier — letting a candidate span
two consecutive segments, scoring candidates on how well they explain the unit's
*opening* rather than the whole unit, vetoing candidates that match only its
tail, and taking the start from the word the first character lands on — all
worked, and all cost more than they returned. The first three share a mechanism:
`idx` advances to just past whatever was chosen, so every neighbour is
downstream of every decision, and gains and losses arrive in adjacent pairs (the
best variant fixes 2.30 s -> 0.02 s at 2:20 on one track and breaks
0.32 s -> 3.70 s at 2:26). The fourth fails differently: placements are already
late (signed mean +0.46 s / +0.21 s) because a sung phrase begins at its breath
and attack, earlier than the first word an ASR will timestamp, so refining into
the segment only adds lateness. See the README for both tables.

Letting the unit size vary — choosing, per step, how many lines this segment
should absorb instead of fixing it up front — was tried next and also measured
worse. It is a tempting move because `pairing` is a rounded average: at 76 lines
over 64 segments the true ratio is 1.19, so a fixed 1 leaves 27 lines unplaced
and a fixed 2 straddles boundaries. Scoring `(k, segment)` jointly does raise
placements (49/76 -> 66/76), and the first-line error barely moves. It is not
free: a unit chosen to maximise similarity will happily straddle a *section*
boundary, and such a unit needs only its tail to match. On the first track the
last verse line scores 0.000 against the hook segment alone and 0.286 once the
following hook line joins it — over the 0.25 threshold — so the breath split
drags that verse line 13.3 s forward into the hook, and displaces the correctly
placed hook line as collateral. Fixed pairing cannot do this at pairing=1: a
one-line unit has no tail to match with. Variable pairing manufactures the very
tail-match pathology that a dedicated veto (above) already failed to fix.

Note the shape of that failure, because it also refutes the reason for trying:
the earlier four attempts all changed *selection* (which segment a unit takes),
so the plan was to change *consumption* instead and avoid the coupling. It does
not avoid it. Consumption sets how fast the segment cursor advances relative to
the line cursor, so it moves `idx` too — just one step removed — and the same
gains-and-losses-in-adjacent-pairs behaviour returns. On the second track, where
the ASR merges two lines consistently, deviating downward orphans the remainder
onto the next segment and shifts every later unit's phase: within-0.5 s falls
26/33 -> 18/33 and the 4x-repeated hook lands a repetition early. Restricting
deviation to *upward* only looks safe, but only because pairing=2 with k<=2
leaves it no room; allowing k<=3 breaks that track the same way (26/33 -> 13/33).

Design philosophy: when a line cannot be confidently matched, we mark it
unmatched rather than inventing a timestamp. Forced aligners always emit an
answer and thus fail *silently* (e.g. drifting into the intro); we prefer honest
gaps that a human — or a later interpolation pass — can fix. The same reasoning
rejects the global matcher above: a visible gap beats a confident wrong time.
The variable-pairing result is the sharpest case: its headline gain was 17 extra
placements, and on the only subset where those extra placements can be checked,
half were catastrophically wrong.
"""
from __future__ import annotations

from .breath import split_words_by_breath
from .charmap import char_timings
from .model import AlignedLine, Segment
from .normalize import default_threshold, similarity


AUTO_PAIRING_MAX = 3


def auto_pairing(lyrics: list[str], segments: list[Segment]) -> int:
    """How many lyric lines the ASR appears to have merged into one segment.

    `pairing` is not a property of the song, it is a property of the *ASR's*
    segmentation, and different models segment differently. faster-whisper
    `medium` merges about two sung lines per segment on Japanese rap, which is
    where the old fixed default of 2 came from — but `large-v3` splits much
    finer (4.7 s average segment down to 2.8 s, 41 segments up to 64 on the same
    four-minute track), so a two-line unit straddles a segment boundary and the
    match degrades. Measured on that track: `large-v3` at the old default is
    *worse* than `medium` (mean 0.50 s -> 1.13 s), and better than it once the
    pairing follows (0.31 s, worst case 3.58 s -> 0.76 s). Upgrading the model
    alone is a trap.

    Lines per segment is exactly what pairing means, so it is also the estimate.
    Capped at 3: beyond that the ASR has stopped producing line-like segments
    (a full mix, where whole verses collapse into one), and the answer there is
    to separate the vocal, not to widen the unit — which the CLI already says.
    """
    if not segments:
        return 1
    return max(1, min(AUTO_PAIRING_MAX, round(len(lyrics) / len(segments))))


def _stanzas(lines: list[str], pairing: int) -> list[list[str]]:
    """Group lyric lines into stanza units of size `pairing` (1 = per line)."""
    if pairing < 1:
        pairing = 1
    return [lines[i:i + pairing] for i in range(0, len(lines), pairing)]


def _containing(start: float, end: float, chars: list[dict] | None) -> tuple[float, float]:
    """Widen a line span so it contains its own character timings.

    A line takes its span from the segment, but the characters are interpolated
    across the *word* timings, and faster-whisper does not guarantee that a
    segment's end equals its last word's end. When it does not, the final
    character runs past the line — which TTML forbids outright ("the timestamp
    of a child element must be completely contained within the timestamp of its
    parent") and which makes a strict player clamp or drop the tail.

    The word timings are the precise signal here, so the line yields to them.
    """
    if not chars:
        return start, end
    return min(start, chars[0]["start"]), max(end, chars[-1]["end"])


def align(
    segments: list[Segment],
    lyrics: list[str],
    *,
    pairing: int | str = "auto",
    threshold: float | None = None,
    window: int = 4,
    karaoke: bool = False,
) -> list[AlignedLine]:
    """Align known `lyrics` lines onto ASR `segments`.

    Args:
        pairing: lyric lines per stanza unit matched to one segment, or "auto"
            (the default) to read it off the ASR's own segmentation — see
            `auto_pairing`, which explains why a fixed value is tied to one
            model. Pass an int to override.
        threshold: minimum character similarity to accept a match. Defaults to a
            script-aware value (see `normalize.default_threshold`).
        window: how many segments ahead to search from the current position.
        karaoke: if True, compute per-character timings (needs word timings).

    Returns one AlignedLine per input lyric line (stanzas are expanded back to
    lines via breath splitting).
    """
    if threshold is None:
        threshold = default_threshold(lyrics)
    if isinstance(pairing, str):
        if pairing != "auto":
            raise ValueError(f"pairing must be an int or 'auto', got {pairing!r}")
        pairing = auto_pairing(lyrics, segments)

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
                    start, end = _containing(seg.start, seg.end, chars)
                    results.append(AlignedLine(line, start, end,
                                               best_score, True, chars))
            else:
                groups = split_words_by_breath(seg.words, unit)
                for line, grp in zip(unit, groups):
                    if grp:
                        chars = char_timings(line, grp) if karaoke else None
                        start, end = _containing(grp[0].start, grp[-1].end, chars)
                        results.append(AlignedLine(line, start, end,
                                                   best_score, True, chars))
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
