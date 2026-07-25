# lyric-align

[![PyPI](https://img.shields.io/pypi/v/lyric-align)](https://pypi.org/project/lyric-align/)
[![Python](https://img.shields.io/pypi/pyversions/lyric-align)](https://pypi.org/project/lyric-align/)
[![tests](https://github.com/ijuinryukichi/lyric-align/actions/workflows/ci.yml/badge.svg)](https://github.com/ijuinryukichi/lyric-align/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/lyric-align)](LICENSE)

**You already have the correct lyrics. You only need the *times*.**

`lyric-align` anchors known lyric lines onto ASR word timings by *character-level*
fuzzy matching, and emits line- or character-level timestamps as **LRC / SRT / ASS / JSON**.

It is built for two things most aligners handle poorly:

- **Space-less languages** (Japanese, Chinese). Word-level tools split on
  whitespace, which does not exist here. `lyric-align` compares characters, so
  it works where `str.split()` fails.
- **Sung vocals, including rap.** ASR mis-hears lyrics constantly, but you don't
  care about its *text* — you have the official lyrics. You only borrow its
  *timing*. Character-level fuzzy matching tolerates the ASR errors and keeps
  the timestamps.

## Install

Python 3.9–3.14. The core has **no dependencies at all**; the ASR extra pulls in
`faster-whisper` (`ctranslate2`, not torch).

**As a command-line tool** (recommended — puts `lyric-align` on your PATH, in its
own isolated environment):

```bash
uv tool install "lyric-align[asr]"
# or: pipx install "lyric-align[asr]"

lyric-align --version
```

Add `separate` to the extras (`lyric-align[asr,separate]`) if you want Demucs
vocal splitting; it pulls in torch, so leave it out until you need it.

**As a library**, into your own environment:

```bash
pip install lyric-align            # core only, pure stdlib — no dependencies
pip install "lyric-align[asr]"     # + faster-whisper, to transcribe audio
```

If you already have segments with word timings from somewhere else, the core
install is enough: feed them in with `--segments` and nothing gets downloaded.

## Use

```bash
# transcribe audio and align known lyrics → LRC
lyric-align song.wav lyrics.txt -o out.lrc

# full mix? split the vocal first — this matters a lot (see below)
lyric-align song.wav lyrics.txt --separate -o out.lrc

# already have Whisper segments? skip ASR
lyric-align --segments segments.json lyrics.txt -f srt

# per-character karaoke ASS (\k tags)
lyric-align song.wav lyrics.txt -f ass --karaoke -o out.ass
```

`lyrics.txt` is plain text, one lyric line per line. Blank lines, `# comments`
and section markers (`[Verse 1]`, `[Hook]`) are skipped, so a pasted lyric sheet
works as-is. `segments.json` is a list of
`{"start", "end", "text", "words": [{"start","end","word"}]}` — the shape any
Whisper flavor produces.

## Output: pick the format your next tool eats

`-f all -o out` writes every format at once.

| format | what it is | where it goes next |
|---|---|---|
| `lrc` | line-timed lyrics | music players; contributing to [LRCLIB](https://lrclib.net) |
| `elrc` | LRC A2 — same file, inline per-syllable timestamps | word-by-word players (AIMP, QQ/NetEase/Kugou, Chronograph), karaoke editors |
| `srt` | universal subtitles | `ffmpeg`, video editors, YouTube captions |
| `vtt` | WebVTT | HTML5 `<track>`, web players |
| `ass` | styling + `\k` karaoke sweeps | Aegisub, `ffmpeg` burn-in |
| `ttml` | per-syllable rich lyrics | Apple-style / AMLL-ecosystem players |
| `aud` | Audacity label track (`start⇥end⇥text`) | **fixing the timings by hand**, then `--from-labels` back into any format; also plain TSV |
| `json` | everything, including scores and unmatched lines | your own code |

Per-syllable formats split by script: alphabetic text is grouped into words
(`<00:06.60>Amazing <00:08.82>grace`), CJK stays one unit per character
(`<00:21.78>治<00:21.94>部`), which is how per-character karaoke formats treat
Japanese and Chinese. The separator between units is taken from the source line
rather than inferred, so a Japanese line that carries a phrasing space
(`硫黄が満ちる 道の奥`) rebuilds character-for-character instead of gaining a
space between every character.

`lrc`/`elrc` cannot express an end time — the last syllable of a line has no
close. Every other format carries the end times this aligner computes.

The `ttml` output is checked against the AMLL reference parser
([`@applemusic-like-lyrics/ttml`](https://github.com/amll-dev/applemusic-like-lyrics)),
not just against the XML schema: lines, per-unit text and millisecond timings
survive a real parse unchanged, in both scripts. It declares a single
`ttm:agent` because the spec wants one per line, and carries `xml:lang` from
`--language`. The title/artist/album an AMLL *database submission* also wants
are deliberately absent — this tool is handed audio and lyrics and nothing else,
so it does not invent them.

### Recipes

```bash
# burn subtitles into a video
ffmpeg -i video.mp4 -vf "ass=out.ass" -c:a copy out.mp4

# karaoke sweep instead of plain lines
lyric-align song.wav lyrics.txt -f ass --karaoke -o out.ass

# fix a mistimed line by hand — the correction loop, in three steps
lyric-align song.wav lyrics.txt -f aud -o out.labels.txt   # 1. export labels
#   2. Audacity: File > Import > Labels, drag the wrong line over the waveform,
#      then File > Export > Export Labels
lyric-align --from-labels out.labels.txt -f lrc -o final.lrc   # 3. back to LRC

# web player
lyric-align song.wav lyrics.txt -f vtt -o out.vtt

# a file shaped for an AMLL TTML DB submission
lyric-align song.wav lyrics.txt -f ttml -o out.ttml \
  --meta musicName="Song" --meta artists="Artist" --meta album="Album" \
  --meta ncmMusicId=1234567
```

The [AMLL TTML DB](https://github.com/amll-dev/amll-ttml-db) is the largest open
collection of word-by-word lyric files — tens of thousands of them, timed by
hand. Its checker requires `musicName`, `artists`, `album` and at least one
platform id (`ncmMusicId` / `appleMusicId` / `spotifyId` / `qqMusicId`), none of
which can be inferred from audio and lyrics, so `--meta` is how you supply them.
Everything else was already in the right shape: one `<span>` per CJK character,
spaces as text nodes *between* spans (the form their spec calls most compliant),
and every child timestamp contained by its parent.

Checked, not assumed — the output parses with the AMLL reference parser
(`@applemusic-like-lyrics/ttml`) and clears every rule in the database's own
checker (`scripts/lyric_checker_bot/src/validator.rs`): 70 lines, 623 syllables,
metadata read back intact. Without `--meta` the same file fails on exactly the
four metadata rules, which is the point of the flag.

Formats deliberately left out: UltraStar `.txt` and CDG need sung **pitch**, not
just timing — [UltraSinger](https://github.com/rakuri255/UltraSinger) and
[karaoke-gen](https://github.com/nomadkaraoke/karaoke-gen) cover that. Apple
Music and Spotify do not accept user-supplied lyric files at all.

### Try it in one minute

Both the recording and the lyrics below are public domain, so this runs
end-to-end with nothing of your own:

```bash
curl -L -o amazing_grace.mp3 \
  "https://upload.wikimedia.org/wikipedia/commons/8/8f/Amazing_Grace_%28vocalist_with_guitar%29_-_Southern_Aire_-_United_States_Air_Force_Reserve_Band.mp3"
# examples/amazing_grace.txt ships with this repo
lyric-align amazing_grace.mp3 examples/amazing_grace.txt \
  --language en --pairing 1 --no-vad -o amazing_grace.lrc
```

```
segments: 12
match threshold: 0.5 (alphabetic script)
aligned 12/12 lines
```

```
[00:06.60]Amazing grace, how sweet the sound
[00:14.30]That saved a wretch like me
[00:23.70]I once was lost, but now am found
[00:34.52]Was blind, but now I see
...
[01:46.24]We've no less days to sing God's praise
[01:57.46]Than when we first begun
```

Note `--no-vad`: this is a slow hymn, and the ASR's voice-activity filter
mistakes sustained singing for silence. With the filter on, the same file yields
**one** garbage segment for 130 seconds; with it off, twelve clean ones. Keep the
filter for rap, drop it for anything sung slowly. (The `--pairing 1` is what
`auto` picks here anyway — this ASR already split one lyric line per segment.)

Drop `--no-vad` and you can watch the honest-gap contract hold: every line is
reported unmatched, nothing is written, and the cause is named.

```
only 0/12 lines matched from 1 segments — try --no-vad (the voice-activity
filter silences slow singing), or --separate (a full mix hides the vocal
from the ASR)
```

### Feed it a vocal stem

Alignment quality is dominated by this one choice. Same track, same settings,
20 human-marked lines — only the input differs:

| input | matched | mean \|err\| |
|---|---|---|
| Demucs vocal stem | **19/20** | **0.50 s** |
| full mix | 8/20 | 1.59 s |

On the full mix the ASR returned 11 segments for a 4-minute song instead of 41,
merging whole sections, and everything past the first chorus went unmatched. Use
`--separate` (or point the tool at a stem you already have). Separation is the
slow step, so the stem is cached and reused.

### Library

```python
from lyric_align import align, Segment

segments = [Segment.from_dict(d) for d in whisper_output]
aligned = align(segments, lyric_lines, karaoke=True)  # pairing="auto"
for a in aligned:
    print(a.start, a.matched, a.line)
```

## Design: honest gaps over silent drift

When a line can't be confidently matched, `lyric-align` marks it **unmatched**
rather than inventing a timestamp. Forced aligners always emit an answer and so
fail *silently* — drifting into the intro, or smearing a chorus. For a
review-in-the-loop workflow (subtitling, MV production) an honest gap you can
see beats a wrong number you can't. Pass `--interpolate` if you do want gaps
filled (they stay flagged as guessed).

## How it works

1. **(optional) vocal separation** — Demucs, if installed (`[separate]`).
2. **ASR** — faster-whisper with word timestamps (`[asr]`), or bring your own segments.
3. **anchor** — each known lyric line/stanza is matched to a segment by
   character-level similarity, scanning forward monotonically so repeated
   choruses consume segments in order.
4. **breath split** — when one segment covers several lines, they're cut at the
   largest inter-word silence (a breath), near the split point implied by
   character counts.
5. **char map** — known characters are distributed across the word span by
   proportional interpolation, for karaoke `\k` timing.

The core (steps 3–5) is **pure Python standard library** — no numpy, no torch.
The heavy pieces (Whisper, Demucs) are optional extras behind lazy imports.

## Where this came from

This was written to put lyrics on the timeline for a set of music videos, where
the lyrics are Japanese and the delivery is rap. That is the whole reason the
matcher compares characters instead of words, and why the accuracy below is
measured on sung Japanese rather than on read speech.

The two tracks the numbers come from are
[過ぎたるもの](https://youtu.be/cpXhuZK5rug) (20 lines, ±0.5 s ground truth) and
[黒砂の誓い](https://youtu.be/b8mjRge4Ffk) (33 lines, 1 s granularity). Others
from the same catalogue: [六の巷](https://youtu.be/OIonX0bZjmI),
[永遠の炎](https://youtu.be/lZIW59t9O-M) — [toryu.tokyo](https://toryu.tokyo).

Short lyric fragments from those tracks appear in the test fixtures. They are the
author's own work and are **not** covered by this project's MIT license — see
[NOTICE](NOTICE). The runnable example (`examples/amazing_grace.txt`) is public
domain, so anyone can reproduce it end to end.

## Accuracy

Measured against 20 human-marked lyric lines of a 4-minute Japanese rap track
(±0.5 s ground-truth precision), aligning from a Demucs-separated vocal stem:

| method | matched | mean \|err\| | median | ≤0.5 s | ≤1.0 s |
|---|---|---|---|---|---|
| **lyric-align** (faster-whisper medium + fuzzy anchor) | 19/20 | 0.50 s | **0.36 s** | **14/20** | 18/20 |
| stable-ts `align()` (known text, now archived) | 20/20 | **0.43 s** | 0.43 s | 12/20 | **19/20** |
| WhisperX ja (transcribe + wav2vec2) | 4/20 | 47 s | 30.7 s | 0/20 | 1/20 |

`lyric-align` and `stable-ts` are practically equivalent: they split the columns,
and every gap between them is smaller than the ±0.5 s the ground truth was
eyeballed to. WhisperX's batched VAD
merges whole verses into single segments, which is fine for captions but loses
line-level timing (and it can't take known text as input).

A second track (3-minute Japanese rap, 33 human-marked lines, 1 s ground-truth
granularity) reproduces this: **33/33 matched, median |err| 0.30 s**, 26/33
within 0.5 s. Its mean of 0.94 s comes almost entirely from four outliers, all on
the *same* line — see below.

The ground truth on both tracks is marked per two-line pair, so these figures
score the *first* line of each pair — 20 and 33 lines, not every line placed.
Second lines have a weaker but free check: each must start inside its pair's
window. The shipped configuration passes it (19/19 and 29/33, the four misses
being the repeated hook already described), so the tables are not hiding a second
failure mode — but the distinction matters as soon as a change is judged on how
many lines it places, because placements land mostly on the unscored half. One
did, and it is the last entry in [Known limits](#known-limits).

### A bigger ASR model is a trap unless the pairing follows

Lines are matched in stanza units, and `pairing` says how many lyric lines make
one unit. That is not a property of the song — it is a property of **the ASR's
segmentation**, and models differ. On the same four-minute track:

| model | segments | mean segment | pairing | mean \|err\| | ≤0.5 s | worst | lines placed |
|---|---|---|---|---|---|---|---|
| `medium` | 41 | 4.73 s | 2 | 0.50 s | 14/20 | 3.58 s | **74/76** |
| `large-v3` | 64 | 2.78 s | **1** | **0.31 s** | **15/20** | **0.76 s** | 49/76 |
| `large-v3` | 64 | 2.78 s | 2 | 1.13 s | 10/20 | 3.70 s | 68/76 |

`large-v3` transcribes visibly better, and with the pairing it deserves it
**removes the 3.6 s outlier entirely** — worst case 3.58 s → 0.76 s, mean down
39 %. Left at a pairing tuned for `medium`, the same upgrade is *worse than not
upgrading*, because a two-line unit now straddles a segment boundary.

**Read the last column before switching.** At pairing 1 there are only 64
segments for 76 lines, so a quarter of them cannot place at all — that row is
more accurate *and* much less complete. Both `large-v3` rows match the same 18
of the 20 measured lines; the extra lines pairing 2 places are ones the ground
truth cannot check, and that configuration also produces six measurable
outliers against pairing 1's none. Which trade you want depends on whether you
are hand-correcting afterwards. `medium` remains the default because 74/76 with
one bad line is the better starting point for most people.

So the default is `--pairing auto`, which reads lines-per-segment off the ASR
output. On every case measured it matches or beats the old fixed 2:

| | lines / segments | auto picks | vs. fixed 2 |
|---|---|---|---|
| 過ぎたるもの, `medium` | 76 / 41 | 2 | identical |
| 過ぎたるもの, `large-v3` | 76 / 64 | **1** | 0.50 s → **0.31 s** |
| 黒砂, `medium` | 80 / 46 | 2 | identical |
| 黒砂, `large-v3` | 80 / 46 | 2 | identical |
| 過ぎたるもの, full mix (ASR collapsed) | 76 / 11 | 3 (capped) | no worse |

It does **not** rescue the repeated-hook track: `large-v3` is behind `medium`
there at every pairing, because four identical hook lines carry no information
about which repetition they are, whatever transcribes them. Better ASR fixes
outliers caused by *garbled text*; it cannot fix outliers caused by *identical*
text.

### Against Vilm, the one other maintained tool here

[Vilm Lyrics Aligner](https://github.com/banjuman/vilm-lyrics-aligner) solves the
same problem for a different audience — live performance, Korean/English
code-switching, SRT into DaVinci Resolve, with a GUI and a Resolve panel where
this has a CLI. Same two tracks, from vocal stems, same ASR model size on both
sides:

| | 過ぎたるもの (no repeats) ||| 黒砂の誓い (4× repeated hook) |||
|---|---|---|---|---|---|---|
| | mean | ≤0.5 s | worst | mean | ≤0.5 s | worst |
| **lyric-align** | 0.50 s | **14/20** | 3.58 s | **0.94 s** | **26/33** | **6.36 s** |
| Vilm | 0.50 s | 10/20 | **2.06 s** | 1.46 s | 13/33 | 8.13 s |

Without repeats the means are identical to three decimals and we each take one
column: **their tail is 1.5 s shorter than ours**, our body has four more lines
inside half a second. With a four-times-repeated hook we are ahead two to one.

That second gap is the matcher, not the pipeline. Running *our* ASR output
through *their* matching layer scores 14/33 inside 0.5 s against our 26/33
(mean 1.55 s against 0.94 s) — their matcher is a single global Needleman-Wunsch
over the whole song's characters, and identical repetitions carry identical
similarity, which is the same result [we measured for a global
matcher](#known-limits) before finding theirs.

Two things this settles. **Character-level matching is not a differentiator** —
Vilm compares characters too, and also reports weak matches rather than forcing
them. What actually differs is smaller: a script-aware threshold instead of a
fixed 0.48, and locality instead of global optimality. And **their start
refinement is a genuinely better idea than ours**, gated on two independent
alignments agreeing; it needs a second aligner, which for us means torch, which
is the dependency this project exists to avoid.

### Coming from stable-ts?

[stable-ts](https://github.com/jianfch/stable-ts) was archived on 2026-05-30, its
last commit being "Add note about paused development". The version `pip` installs
is older than that: 2.19.1, from **2025-08**, which predates its own final
alignment work (committed 2025-10, never released).

It did this job well, and this is not a claim to have beaten it. It is also not
a claim to have lost — the head-to-head splits, and every gap in it is smaller
than the ±0.5 s the ground truth was marked to:

| | matched | mean | median | ≤0.5 s | ≤1.0 s | first line |
|---|---|---|---|---|---|---|
| **lyric-align** | 19/20 | 0.50 s | **0.36 s** | **14/20** | 18/20 | **+0.28 s** |
| stable-ts `align()` | 20/20 | **0.43 s** | 0.43 s | 12/20 | **19/20** | −1.64 s |

They take the mean and the count; we take the median and the ≤0.5 s bucket. On a
ground truth eyeballed to half a second, a 0.07 s difference is not a result in
either direction.

The count is a contract, not accuracy. A forced aligner always emits, so
stable-ts places all 20 — and the twentieth is that first line, 1.64 s early,
sitting in the intro. `lyric-align` places 19 and says so about the one where the
ASR collapsed. What actually differs is everything around the accuracy:

| | stable-ts `align()` | lyric-align |
|---|---|---|
| status | archived 2026-05 | maintained |
| install | `torch` + `torchaudio` + `openai-whisper`, unconditionally | **nothing** for the core; `ctranslate2` (via `faster-whisper`) only if you want it to transcribe |
| matching | word-level forced alignment | character-level fuzzy anchor — no whitespace assumption |
| threshold | — | script-aware: 0.25 for CJK, 0.50 for alphabetic |
| a line it cannot place | always given a time | reported as unmatched |
| output | SRT, VTT, ASS, TSV, JSON | LRC, eLRC, SRT, VTT, ASS, TTML, JSON, Audacity labels |

```python
# stable-ts
import stable_whisper
model = stable_whisper.load_model("medium")
result = model.align(audio, "\n".join(lines), language="ja", original_split=True)
result.to_srt_vtt("out.srt")
```

```bash
# lyric-align — format inferred from the extension
lyric-align audio.wav lyrics.txt --language ja -o out.srt
```

The last row is the one to understand before switching. A forced aligner emits a
time for every line, so when it fails it fails *silently* — a line drifts into
the intro and nothing tells you. `lyric-align` leaves that line empty instead.
On error-prone sung ASR that is the point, but if you need a fully populated
timeline anyway, `--interpolate` fills the gaps and keeps `matched: false` on
them so you can still tell which ones were guessed.

### Match threshold is script-aware

A line is accepted when its character similarity clears a threshold, and the
right floor depends on how many characters the language has to choose from. So
the default is picked from the lyrics themselves (`--threshold` overrides it):

| script | default | why |
|---|---|---|
| Japanese / Chinese | 0.25 | true matches against error-prone sung ASR drop as low as 0.26 |
| alphabetic | 0.50 | two *unrelated* English sentences already score 0.28–0.34 |

Using the CJK floor on English silently invents matches — measured on the hymn
above, "Through many dangers, toils and snares" was placed on the line
"We've no less days to sing God's praise" (similarity 0.34).

## Known limits

- **Heavily repeated refrains can land on the wrong repetition.** A hook line
  sung four times is four identical strings; if the ASR segments the repeats
  unevenly, the forward scan can consume the neighbouring one. On the track
  above, one 4×-repeated hook line produced errors of +6.4 s, −3.8 s, −4.5 s and
  +5.7 s while every non-repeated line stayed within ~0.5 s. Check hook sections
  by hand, or align verses and hooks as separate passes.

  Replacing the forward scan with a globally optimal monotone assignment does
  *not* fix this, and measured worse. Identical repetitions carry identical
  similarity, so the global optimum just places more lines — and the extra ones
  land on the wrong cycle:

  | matcher | lines placed | mean \|err\| | within 0.5 s | worst |
  |---|---|---|---|---|
  | forward scan (shipped) | 70/80 | **0.94 s** | **26/33** | **6.4 s** |
  | global optimum | 80/80 | 1.61 s | 22/33 | 10.6 s |
  | global optimum + diagonal-drift penalty | 80/80 | 1.14 s | 25/33 | 10.6 s |

  Telling repetitions apart needs a timing prior, not a better search over
  similarity. Meanwhile the forward window is doing real work: it stops a line
  from reaching a distant segment that happens to clear the threshold.

  A timing prior was then tried, and also measured worse. Scoring candidates by
  `similarity − λ·|start − predicted|`, where `predicted` is the last placement
  plus the running median gap:

  | λ | lines placed | mean \|err\| | within 0.5 s | worst |
  |---|---|---|---|---|
  | 0 (shipped) | 33/33 | **0.94 s** | **26/33** | **6.4 s** |
  | 0.1 | 33/33 | 1.67 s | 21/33 | 10.6 s |
  | 0.3 | 33/33 | 2.05 s | 19/33 | 10.6 s |
  | 0.5 | 8/33 | — | 7/33 | — |

  The prior predicts from the aligner's own previous placements, so it cannot
  correct a bad one — it anchors on it and drags the next lines along, which is
  why the worst case grows rather than shrinks. Songs also do not run at one
  pace: a median gap mispredicts hardest across a section boundary, which is
  exactly where repeated hooks sit.

  Restricting the prior to breaking near-ties (candidates within ε similarity,
  never overturning a clear winner) is the only variant that does not hurt, and
  it does not clearly help either: ε=0.02 moved one line into the ≤0.5 s bucket
  (26→27) and the mean by 0.07 s; ε=0.05 left the buckets alone and cut the
  worst case to 5.7 s; ε=0.10 collapsed back to the harmful regime. The second
  track was unchanged at every ε. A 0.07 s shift is below the 1 s resolution of
  that track's ground truth, so there is no measurement here to ship on — and
  the useful ε sits directly beside a harmful one. Left out.

  A prior that would actually work has to come from a signal independent of the
  aligner's output — audio-side section detection, say — which is a different
  tool with a much heavier dependency than a stdlib core.
- **Correcting one placement tends to break the next one.** The first track's
  worst case (3.6 s) has a fully diagnosed cause: `SequenceMatcher.ratio()`
  divides by *both* strings' lengths, so a short segment matching only the
  second half of a two-line unit outscores the longer segment that actually
  starts it (0.615 vs 0.304; concatenating both gives 0.644, and the right
  answer wins). Three independent fixes follow from that, and a fourth from how
  a global character aligner gets sub-segment resolution. All four fix the
  outlier. All four cost more elsewhere than they return:

  | candidate selection | 過ぎたるもの mean / worst / ≤0.5 s | 黒砂 matched / mean / ≤0.5 s |
  |---|---|---|
  | forward scan (shipped) | **0.50 s** / 3.6 s / **14/20** | **33/33** / **0.94 s** / **26/33** |
  | span up to 2 segments | 0.34 s / **0.7 s** / 15/20 | 29/33 / 2.13 s / 23/33 |
  | score the unit's opening, not the whole unit | 0.34 s / **0.7 s** / 15/20 | 31/33 / 1.22 s / 23/33 |
  | veto candidates matching only the unit's tail | 0.33 s / **0.7 s** / 14/20 | 32/33 / 1.74 s / 19/33 |
  | ↑ but only on lines that never repeat | 0.34 s / **0.7 s** / 15/20 | 32/33 / 1.00 s / 25/33 |

  The mechanism is the scan itself. `idx` advances to just past whatever was
  chosen, so *every* neighbour is downstream of *every* decision. Gains and
  losses arrive in adjacent pairs: the last row above fixes 2.30 s → 0.02 s at
  2:20 on the second track and breaks 0.32 s → 3.70 s at 2:26, six seconds
  later. Across both tracks it nets to two lines fixed, one broken, one turned
  into a gap, on 53 measured lines — which is not an improvement, it is noise.
  Local accuracy does not compose in a greedy monotone scan, and that is why
  four unrelated interventions all land on roughly the same total.

  The fourth is worth naming separately because it is what Vilm does differently
  ([above](#against-vilm-the-one-other-maintained-tool-here)). Taking each line's start from the word
  its first character lands on — the sub-segment resolution a global character
  aligner buys — measured *worse on both tracks* (mean 0.50 → 0.79 s and
  0.94 → 1.26 s; ≤0.5 s 14/20 → 9/20 and 26/33 → 20/33). Placements are already
  late (signed mean +0.46 s and +0.21 s), and refining into the segment can only
  add lateness. A sung phrase begins at its breath and attack, before the first
  word the ASR is willing to timestamp, so the segment boundary is the better
  estimate of onset.
- **A varying unit size places more lines, and some of them badly.** `pairing`
  is a rounded average, so it is wrong for part of any track: at 76 lines over 64
  segments the true ratio is 1.19, and a fixed 1 leaves 27 lines unplaced while a
  fixed 2 straddles boundaries. Choosing `(lines, segment)` jointly at each step
  fixes the placement count and looks nearly free on the shipped metric:

  | unit size | lines placed | mean \|err\| | within 0.5 s | worst | 2nd lines outside their GT window |
  |---|---|---|---|---|---|
  | fixed, from the ASR (shipped) | 49/76 | **0.31 s** | **15/20** | **0.8 s** | **0 of 16** |
  | variable, k ≤ 2 | 66/76 | 0.42 s | 14/20 | 2.0 s | 2 of 18 |
  | variable, k ≤ 2, only if it wins by 0.1 | 66/76 | 0.32 s | **15/20** | **0.8 s** | 1 of 18 (by 13.3 s) |

  The last column is the point. The other columns score only the *first* line of
  each two-line ground-truth pair, which is where the extra placements do *not*
  land — so on the shipped metric the third row is 17 free placements. Checking
  the second lines, which have a known window to fall inside, shows what was
  bought: the last verse line scores 0.000 against the hook segment on its own
  and 0.286 once the following hook line is absorbed into the same unit, clearing
  the 0.25 threshold, so it is placed 13.3 s late inside the hook — and the hook
  line that had been correct is displaced with it. A unit picked to maximise
  similarity will straddle a section boundary, and such a unit needs only its
  tail to match; fixed pairing=1 cannot do this because a one-line unit has no
  tail. Of the two extra placements that can be checked, one is right and one is
  13.3 s wrong.

  On a track where the ASR merges two lines consistently the same move fails
  from the other side: deviating downward orphans the remaining line onto the
  next segment and shifts every later unit's phase, taking within-0.5 s from
  26/33 to 18/33 and landing the 4×-repeated hook a repetition early. Allowing
  only *upward* deviation appears to fix that, but only because pairing=2 with
  k ≤ 2 leaves upward no room — permitting k ≤ 3 breaks the same track again
  (26/33 → 13/33).

  This also disposes of the reason for trying it. The four attempts above all
  changed which segment a unit selects, so the plan here was to change how much
  a unit *consumes* and dodge that coupling. Consumption sets how fast the
  segment cursor advances relative to the line cursor, so it moves `idx` as
  well — one step removed, same result.
- **Slow, sustained singing is much harder than rap** — hymns, ballads and
  school songs stretch vowels until the ASR stops producing usable segments.
  Reach for `--no-vad` first (see the one-minute example); dense, consonant-rich
  delivery is the sweet spot. This is an ASR limit, not an anchoring one.
- **A quiet or lo-fi recording can defeat the ASR entirely.** On a −33 dBFS
  amateur recording of an unaccompanied Japanese art song, Whisper returned zero
  segments, and returned `音楽` ("music") or a row of repeated single characters
  once its silence thresholds were relaxed — it classified the singing as music
  rather than speech. Loudness-normalizing to −16 LUFS did not help. When the
  transcription is empty there is nothing to anchor to; check for segments before
  blaming the alignment.

The nearest match, [stable-ts](https://github.com/jianfch/stable-ts), was
**archived in 2026-05** — see [Coming from stable-ts?](#coming-from-stable-ts)
for what carries over and what does not.

## License

MIT, for the code, tests and documentation. The song lyrics quoted in the test
fixtures are not covered by it — see [NOTICE](NOTICE).
