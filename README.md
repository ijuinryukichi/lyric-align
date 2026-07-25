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
