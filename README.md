# lyric-align

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

Not on PyPI yet — install from the repository.

**As a command-line tool** (recommended — puts `lyric-align` on your PATH, in its
own isolated environment):

```bash
uv tool install "lyric-align[asr] @ git+https://github.com/ijuinryukichi/lyric-align"
# or: pipx install "lyric-align[asr] @ git+https://github.com/ijuinryukichi/lyric-align"

lyric-align --version
```

Add `separate` to the extras (`lyric-align[asr,separate]`) if you want Demucs
vocal splitting; it pulls in torch, so leave it out until you need it.

**As a library**, into your own environment:

```bash
pip install "git+https://github.com/ijuinryukichi/lyric-align"        # core only, pure stdlib
pip install "lyric-align[asr] @ git+https://github.com/ijuinryukichi/lyric-align"
```

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
```

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
filter for rap, drop it for anything sung slowly. (`--pairing 1` because this ASR
already split one lyric line per segment.)

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
aligned = align(segments, lyric_lines, pairing=2, karaoke=True)
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
author's own work and are **not** covered by this project's MIT license; see
[LICENSE](LICENSE). The runnable example (`examples/amazing_grace.txt`) is public
domain, so anyone can reproduce it end to end.

## Accuracy

Measured against 20 human-marked lyric lines of a 4-minute Japanese rap track
(±0.5 s ground-truth precision), aligning from a Demucs-separated vocal stem:

| method | matched | mean \|err\| | ≤1.0 s |
|---|---|---|---|
| **lyric-align** (faster-whisper medium + fuzzy anchor) | 19/20 | 0.50 s | 18/20 |
| stable-ts `align()` (known text, now archived) | 20/20 | 0.42 s | 19/20 |
| WhisperX ja (transcribe + wav2vec2) | 4/20 | 47 s | 1/20 |

Both `lyric-align` and `stable-ts` reach the ±0.5 s noise floor of the human
ground truth — i.e. practically equivalent accuracy. WhisperX's batched VAD
merges whole verses into single segments, which is fine for captions but loses
line-level timing (and it can't take known text as input).

A second track (3-minute Japanese rap, 33 human-marked lines, 1 s ground-truth
granularity) reproduces this: **33/33 matched, median |err| 0.30 s**, 26/33
within 0.5 s. Its mean of 0.94 s comes almost entirely from four outliers, all on
the *same* line — see below.

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
**archived in 2026-05**. `lyric-align` is a lighter (`ctranslate2`, not
`torch`), maintained take on the same "I have the text, I need the times" job,
with a CJK-first matcher and honest-gap semantics.

## License

MIT
