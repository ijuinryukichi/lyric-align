# Five ways I failed to fix a 3.6-second error

`lyric-align` places lyrics you already have onto a timeline. You give it the
official words and some audio; it borrows the timings from an ASR transcript and
throws the ASR's text away, because for sung Japanese the text is wrong and the
timings are not.

It works. On a 4-minute rap track measured against 20 human-marked lines it
places 19 of them, mean error 0.50 s, which is the noise floor of the ground
truth itself. On a second track, 33 of 33, median 0.30 s.

One line was 3.6 seconds off. This is the story of failing to fix it five times,
and of the thing that was actually wrong — which turned out not to be that line.

## The diagnosis was easy

Lines are matched in pairs against ASR segments by character similarity, using
Python's `SequenceMatcher.ratio()`. The offending unit is 27 characters. Two
segments compete for it:

| candidate | starts at | length | similarity |
|---|---|---|---|
| the correct one | 28.90 s | 21 chars | **0.304** |
| the one that wins | 32.08 s | 13 chars | **0.615** |

The wrong segment is later and *shorter*, and it matches the unit's second half.
`ratio()` divides by the length of both strings, so a short segment that lines up
with part of a long unit scores higher than a long segment that lines up with a
different part. The winner isn't more similar in any sense a human would mean. It
is just smaller.

Concatenate the two candidates and compare the pair against the unit: 0.644. The
right answer wins. The fix writes itself.

## Fix 1: let a candidate span two segments

ASR does not break where lyrics break, so a two-line unit is often split across a
segment boundary. Let each candidate be one segment, or two consecutive ones, and
take whichever scores best.

It worked exactly as predicted. Worst error 3.58 s → 0.70 s, mean 0.50 → 0.34,
one more line inside 0.5 s. Nothing else on that track moved.

On the other track it was a disaster: 33 placements → 29, mean 0.94 → 2.13 s,
worst 6.4 → 20.5 s. Consuming two segments per unit races through a
four-times-repeated hook and runs out of song.

Requiring the two-segment candidate to beat the one-segment candidate by a margin
looked like the obvious repair. There is no margin that works. At 0.02 the first
track is fixed and the second is still down four placements; by 0.1 the second
track is back to its baseline buckets and the fix on the first has vanished. The
window between them is empty.

## Fix 2: ask whether the segment explains the unit's *opening*

Back to the diagnosis. The wrong candidate matched the unit's tail. But we are
extracting a **start time** — so the question was never "how similar are these
two strings", it was "does this segment contain the beginning of this line?"

Compare the segment against an equally long prefix of the unit. Length-matched,
so `ratio()`'s bias disappears, and it asks the right question directly.

Same result. First track fixed identically (3.58 → 0.70). Second track degraded
again: 33 → 31 placements, mean 0.94 → 1.22, lines inside 0.5 s from 26 to 23.

## Fix 3: veto instead of re-score

Both failures had re-scored *every* candidate, which moves correct matches too.
So: keep the original scoring, and only reject a winner whose matched region
begins deep inside the unit — a targeted veto on the pathology, nothing else.

Worse than either. The second track fell to 21 lines inside 0.5 s at the mildest
setting and kept falling.

The reason is worth keeping. In error-prone sung ASR, *where* a match begins
carries almost no signal, because the beginning of a sung phrase is precisely
where the ASR is least reliable — breath, attack, consonants swallowed into the
downbeat. "The match starts late" is not a marker of a bad candidate. It is the
normal condition of a good one.

## Fix 4: apply it only where it cannot hurt

Locality only matters because of repetition. If a unit's text appears exactly
once in the song, there is no repetition hazard, so the better scoring should be
free there. Gate on it.

This was the good one. First track fixed. Second track recovered most of the
loss — mean 1.00 s against the baseline's 0.94, 25 lines inside 0.5 s against 26.

It changed exactly three lines on that track:

| ground truth | baseline | gated |
|---|---|---|
| 2:20 | +2.30 s | **+0.02 s** |
| 2:26 | −0.32 s | **−3.70 s** |
| 1:29 | −0.12 s | unmatched |

Read those two top rows again. The line at 2:20 was fixed. The line six seconds
later, which had been correct, broke by the same order of magnitude.

## The thing that was actually wrong

The matcher scans forward from a cursor. When a unit is placed, the cursor
advances past the chosen segment, so **every line is downstream of every previous
decision.** Correcting a placement does not just correct it — it moves the search
origin for the line after it.

So gains and losses arrive in adjacent pairs. Across both tracks, the best
variant nets to two lines fixed, one broken, one turned into a gap, on 53
measured lines. That is not an improvement. That is noise with a good story
attached.

And it retroactively explains two earlier failures I had filed separately. A
globally optimal monotone assignment measured worse. A timing prior — score
candidates by `similarity − λ·|start − predicted|` — measured worse at every λ.
I had written down a different reason for each. There was one reason: **local
accuracy does not compose in a greedy monotone scan.** Four unrelated
interventions land on the same total because the errors are not independent.

## Fix 5, which fails differently

The one comparable tool in this niche takes a different route: concatenate the
whole song into one character stream, align it globally, and read each line's
start from the character it maps to. That buys sub-segment resolution — a start
time from inside a segment rather than from its edge.

I did not adopt their architecture, but I could steal the resolution: keep my
segment selection, then refine the start to the word the line's first character
lands on. Selection unchanged, cursor unchanged — structurally immune to the
coupling that killed the other four.

It was worse on both tracks. Mean 0.50 → 0.79 s and 0.94 → 1.26 s; lines inside
0.5 s from 14/20 to 9/20 and from 26/33 to 20/33.

The signed errors say why. Placements were already **late** — mean +0.46 s and
+0.21 s — and refining into a segment can only push later still. A sung phrase
begins at its breath and its attack, before the first word an ASR is willing to
timestamp. The segment boundary is the worse-looking number and the better
estimate of onset.

Which also explains a benchmark result I had found puzzling: the global aligner
reaches the same mean as mine while landing fewer lines inside 0.5 s. Its
resolution buys a shorter tail and costs it the body. That is not a bug in either
tool. It is the trade.

## What would actually work

Not better search over similarity — that was the DP result. Not a prior derived
from the aligner's own output — that was the timing-prior result; it predicts
from previous placements, so it cannot correct a bad one, it anchors on it.

It needs a signal that is *independent* of the alignment. The tool mentioned
above does exactly this, and the design is worth naming: it runs two alignments,
and only moves a start when they agree — specifically when both agree on where
the phrase **ends** while disagreeing about where it begins, which is the
signature of a line swallowed by the previous sustained vowel, as distinct from
a line that simply drifted.

That is the right shape. It also costs a second aligner, which for this project
means torch, which is the dependency this project exists to avoid. Identified,
priced, declined — and written down, so the next person can skip the afternoon.

## Notes for anyone measuring something similar

**Two tracks, minimum.** Every one of the five fixes looks adoptable on the first
track alone: worst case cut by 2.9 seconds, not a single line made worse. The
entire cost sits on the other song.

**Know your ground truth's resolution.** One of these tracks is marked to ±0.5 s
by eye, the other to 1 s. A 0.07 s improvement on the second is not a small
result, it is not a result. Two candidate changes died on this rule alone.

**Your diagnostic will trip on the bug you are diagnosing.** A probe written to
count misplaced repeated hooks matched each unit to its most similar ground-truth
line. Every repetition of a hook is the same string, so all four collapsed onto
the first, and the probe reported eleven failures where there was one. It failed
for the *same reason* the DP failed — identical text carries no information about
which repetition it is. When a result is surprisingly bad, suspect the
instrument first.

---

Every number here is reproducible from cached ASR output; the sweeps are in the
benchmark harness, and the shipped matcher is unchanged. The outlier is still
3.6 seconds. I know exactly why, and I know what it costs to fix.
