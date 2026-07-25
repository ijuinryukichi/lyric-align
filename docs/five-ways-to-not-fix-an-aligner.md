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

## An aside: the one other tool doing this

[Vilm Lyrics Aligner](https://github.com/banjuman/vilm-lyrics-aligner) appeared
while I was working on this. It solves the same problem — your lyrics, its
timings — for a different audience: live performance, Korean/English
code-switching, SRT into DaVinci Resolve. It has a GUI and an editor panel; this
has a CLI. It is also, as far as I can find, the only other maintained thing in
this niche, so it is the only real check on whether any of my choices are load
bearing.

Its matcher takes the route I did not: concatenate the entire song into one
character stream, concatenate the ASR into another, and run a single semi-global
Needleman-Wunsch over the pair. Each line then reads its start from whichever
character it mapped to — sub-segment resolution, where mine snaps to a segment
edge.

Run against the same two tracks, from vocal stems, with the same ASR model size
on both sides:

| | 過ぎたるもの (no repeats) | | | 黒砂の誓い (4× hook) | | |
|---|---|---|---|---|---|---|
| | mean | ≤0.5 s | worst | mean | ≤0.5 s | worst |
| lyric-align | 0.50 s | **14/20** | 3.58 s | **0.94 s** | **26/33** | **6.36 s** |
| Vilm | 0.50 s | 10/20 | **2.06 s** | 1.46 s | 13/33 | 8.13 s |

On the track without repeats the means are identical to three decimals, and we
each win one column: their tail is 1.5 s shorter than mine, my body has four more
lines inside half a second. On the track with a four-times-repeated hook I am
ahead two to one.

That second gap is the matcher, not the pipeline. Feeding **my** ASR output
through **their** matching layer and scoring the result the same way: 14/33
inside 0.5 s against my 26/33, mean 1.55 s against 0.94 s. Global optimality over
identical characters cannot tell the third chorus from the fourth — which is the
DP result from earlier in this post, arrived at independently by someone else's
code.

It also demolishes a line I had been telling myself. "Character-level matching for
space-less languages" is not a differentiator; Vilm compares characters too, and
reports weak matches instead of forcing them, same as I do. The things that
actually differ are smaller and duller: a script-aware threshold instead of a
fixed 0.48, and locality instead of global optimality.

## Fix 5, which fails differently

So: steal the resolution without the architecture. Keep my segment selection,
then refine each start to the word the line's first character lands on. Selection
unchanged, cursor unchanged — structurally immune to the coupling that killed the
other four.

It was worse on both tracks. Mean 0.50 → 0.79 s and 0.94 → 1.26 s; lines inside
0.5 s from 14/20 to 9/20 and from 26/33 to 20/33.

The signed errors say why. Placements were already **late** — mean +0.46 s and
+0.21 s — and refining into a segment can only push later still. A sung phrase
begins at its breath and its attack, before the first word an ASR is willing to
timestamp. The segment boundary is the worse-looking number and the better
estimate of onset.

Which also explains the split decision in the table above. Vilm's character-level
resolution buys the shorter tail — it can start a line inside a segment, so a
badly-bounded segment hurts it less — and costs it the body, because every start
it refines lands after the breath. My segment edges look cruder and sit closer to
where the singing begins. Neither is a bug. It is the trade, and it runs in both
directions.

## What would actually work

Not better search over similarity — that was the DP result. Not a prior derived
from the aligner's own output — that was the timing-prior result; it predicts
from previous placements, so it cannot correct a bad one, it anchors on it.

It needs a signal that is *independent* of the alignment. Vilm does exactly this,
and it is the best idea I found in anyone's code this month: it runs **two**
alignments — a local one from the ASR, a global forced one over the whole song —
and moves a start only when they agree. Specifically, when both agree on where
the phrase **ends** while disagreeing about where it begins. That difference is
the signature of a line swallowed by the previous sustained vowel, and it is
distinguishable from a line that merely drifted, for which both ends move
together. Two sources of evidence, and a rule for when to believe them.

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
