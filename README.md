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

```bash
pip install lyric-align          # core (pure stdlib, no heavy deps)
pip install lyric-align[asr]      # + faster-whisper, to transcribe audio
```

## Use

```bash
# transcribe audio and align known lyrics → LRC
lyric-align song.wav lyrics.txt -o out.lrc

# already have Whisper segments? skip ASR
lyric-align --segments segments.json lyrics.txt -f srt

# per-character karaoke ASS (\k tags)
lyric-align song.wav lyrics.txt -f ass --karaoke -o out.ass
```

`lyrics.txt` is plain text, one lyric line per line. `segments.json` is a list
of `{"start", "end", "text", "words": [{"start","end","word"}]}` — the shape any
Whisper flavor produces.

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

The nearest match, [stable-ts](https://github.com/jianfch/stable-ts), was
**archived in 2026-05**. `lyric-align` is a lighter (`ctranslate2`, not
`torch`), maintained take on the same "I have the text, I need the times" job,
with a CJK-first matcher and honest-gap semantics.

## License

MIT
