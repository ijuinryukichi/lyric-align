"""Command-line interface.

    lyric-align AUDIO LYRICS.txt -o out.lrc          # transcribe + align
    lyric-align AUDIO LYRICS.txt --separate -o o.lrc  # split vocals first (better)
    lyric-align --segments segs.json LYRICS.txt -f ass --karaoke
    lyric-align --from-labels fixed.labels.txt -f lrc  # convert corrected labels

LYRICS is a plain-text file, one lyric line per line. Blank lines and section
markers ([Verse 1], [Hook]) are ignored, so pasted lyric sheets work as-is.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from .anchor import align, interpolate_gaps
from .formats import EXTENSIONS, FORMATTERS, NEEDS_SYLLABLES, from_aud
from .model import Segment
from .normalize import CJK_THRESHOLD, LATIN_THRESHOLD, default_threshold

SECTION_MARKER = re.compile(r"^[\[(](?:[^\[\]()]{0,40})[\])]$")


def read_lyrics(path: Path) -> list[str]:
    """One lyric line per line; drop blanks, section markers and # comments."""
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or SECTION_MARKER.match(line):
            continue
        out.append(line)
    return out


def load_segments(path: Path) -> list[Segment]:
    return [Segment.from_dict(d) for d in json.loads(path.read_text())]


DESCRIPTION = """\
Place known lyrics on an audio timeline.

You already have the correct lyrics; you only need the times. lyric-align
anchors your lyric lines onto ASR word timings by character-level fuzzy
matching — built for space-less languages (Japanese, Chinese) and for sung
vocals, where the ASR mis-hears the words but still times them well.

Lines it cannot confidently place are reported as unmatched instead of being
given an invented timestamp.

examples:
  lyric-align song.wav lyrics.txt -o out.lrc              transcribe and align
  lyric-align song.wav lyrics.txt --separate -o out.lrc   split vocals first (better on a mix)
  lyric-align song.mp3 lyrics.txt --language en --no-vad  English, sung slowly
  lyric-align --segments segs.json lyrics.txt -f ass --karaoke
  lyric-align --from-labels fixed.labels.txt -f lrc   convert labels you corrected

LYRICS is plain text, one lyric line per line. Blank lines, # comments and
section markers ([Verse 1], [Hook]) are skipped, so a pasted lyric sheet works
as-is.

To fix a timing by hand, write '-f aud', drag the line over the waveform in
Audacity, export the labels, and read them back with --from-labels.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lyric-align", description=DESCRIPTION,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", nargs="?", help="audio file (omit if --segments given)")
    p.add_argument("lyrics", nargs="?", help="plain-text lyrics, one line per line")

    out = p.add_argument_group("output")
    out.add_argument("-o", "--output", help="output path (default: stdout)")
    out.add_argument("-f", "--format", default=None,
                     choices=sorted(FORMATTERS) + ["all"],
                     help="output format (default: infer from -o, else json). "
                          "'all' writes every format next to -o")
    out.add_argument("--karaoke", action="store_true",
                     help="per-character timings, for karaoke \\k tags (ass/json). "
                          "Always on for elrc/ttml, which are per-syllable formats")
    out.add_argument("-q", "--quiet", action="store_true", help="suppress progress reporting")
    out.add_argument("--from-labels", metavar="FILE",
                     help="read an Audacity label track instead of aligning, and "
                          "convert it to -f. This closes the correction loop: export "
                          "'aud', drag the wrong lines over the waveform in Audacity, "
                          "export the labels again, and turn them back into LRC/TTML/"
                          "anything. Takes no AUDIO or LYRICS — the labels hold both")

    asr = p.add_argument_group(
        "transcription", "ignored when --segments is given")
    asr.add_argument("--segments", help="pre-computed segments JSON (skip ASR entirely)")
    asr.add_argument("--separate", action="store_true",
                     help="split the vocal stem with Demucs first (needs the [separate] "
                          "extra). Slow, cached, and markedly more accurate on a full mix")
    asr.add_argument("--language", default="ja",
                     help="ASR language code (default: %(default)s — set this for "
                          "anything but Japanese)")
    asr.add_argument("--model", default="medium",
                     help="faster-whisper model size (default: %(default)s)")
    asr.add_argument("--device", default="cpu",
                     help="ASR compute device: cpu or cuda (default: %(default)s). "
                          "Apple Silicon has no ctranslate2 GPU backend — keep cpu")
    asr.add_argument("--no-vad", dest="vad", action="store_false",
                     help="disable the voice-activity filter. The filter helps on dense "
                          "delivery (rap) but silences slow, sustained singing — if you "
                          "get few or no segments, try this first")

    al = p.add_argument_group("alignment")
    al.add_argument("--pairing", type=int, default=2,
                    help="lyric lines per stanza unit matched to one segment "
                         "(default: %(default)s; use 1 if the ASR splits per line)")
    al.add_argument("--interpolate", action="store_true",
                    help="give unmatched lines guessed timestamps between their "
                         "neighbours (they stay flagged as unmatched)")
    al.add_argument("--threshold", type=float, default=None,
                    help="minimum character similarity to accept a match, 0-1. Default "
                         f"depends on the script of the lyrics: {CJK_THRESHOLD} for "
                         f"Japanese/Chinese, {LATIN_THRESHOLD} for alphabetic scripts, "
                         "where unrelated sentences score far higher by chance")
    al.add_argument("--window", type=int, default=4,
                    help="how many segments ahead to search for each line "
                         "(default: %(default)s; raise it if the ASR drops segments)")

    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Both positionals are optional, so argparse fills AUDIO first. A lone
    # positional can only be the lyrics — there is no aligning audio without
    # them — so hand it over rather than reporting a missing LYRICS.
    if args.lyrics is None and args.audio is not None:
        args.audio, args.lyrics = None, args.audio

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    for label, path in (("lyrics", args.lyrics), ("audio", args.audio),
                        ("segments", args.segments), ("labels", args.from_labels)):
        if path and not Path(path).exists():
            print(f"error: {label} file not found: {path}", file=sys.stderr)
            return 2

    fmt = args.format
    if fmt is None and args.output:
        fmt = Path(args.output).suffix.lstrip(".").lower()
    if fmt != "all" and fmt not in FORMATTERS:
        fmt = "json"
    if fmt == "all" and not args.output:
        print("error: -f all needs -o to name the files to write", file=sys.stderr)
        return 2
    targets = sorted(FORMATTERS) if fmt == "all" else [fmt]
    # Per-syllable formats are pointless without character timings, so turn them
    # on for those rather than silently emitting line-level output.
    karaoke = args.karaoke or bool(NEEDS_SYLLABLES.intersection(targets))

    if args.from_labels:
        # Converting a corrected label track: the file already holds the text and
        # the times, so there is nothing to transcribe and nothing to match.
        try:
            aligned = from_aud(Path(args.from_labels).read_text())
        except ValueError as e:
            print(f"error: {args.from_labels}: {e}", file=sys.stderr)
            return 2
        if not aligned:
            print(f"error: no labels found in {args.from_labels}", file=sys.stderr)
            return 2
        log(f"labels: {len(aligned)} (from {args.from_labels})")
        if karaoke:
            # Labels are line-level; per-syllable output would have to be invented.
            log("note: a label track carries no per-character timings, so "
                f"{'/'.join(sorted(NEEDS_SYLLABLES.intersection(targets))) or 'karaoke'} "
                "output stays line-level")
        return _write(args, fmt, targets, aligned, karaoke, log)

    if not args.lyrics:
        print("error: provide LYRICS (or --from-labels to convert a label track)",
              file=sys.stderr)
        return 2
    lyrics = read_lyrics(Path(args.lyrics))
    if not lyrics:
        print(f"error: no lyric lines found in {args.lyrics}", file=sys.stderr)
        return 2

    if args.segments:
        segments = load_segments(Path(args.segments))
        log(f"segments: {len(segments)} (from {args.segments})")
    elif args.audio:
        audio = args.audio
        try:
            if args.separate:
                from .separate import separate_vocals
                log("separating vocals (Demucs) — this is the slow step, result is cached ...")
                audio = separate_vocals(audio)
                log(f"vocal stem: {audio}")
            from .asr import transcribe
        except ImportError as e:
            # Missing optional extra: report the one-line install hint, not a traceback.
            print(f"error: {e}", file=sys.stderr)
            return 3
        log(f"transcribing with faster-whisper ({args.model}, {args.language}"
            f"{'' if args.vad else ', vad off'}) ...")
        segments = transcribe(audio, language=args.language, model_size=args.model,
                              device=args.device, vad=args.vad)
        log(f"segments: {len(segments)}")
        if not segments and args.vad:
            # The voice-activity filter is tuned for dense delivery; on sustained
            # singing it can swallow the whole track. Retry once, loudly, rather
            # than reporting "0 lines aligned" and leaving the cause unexplained.
            log("no segments with the voice-activity filter — retrying with --no-vad ...")
            segments = transcribe(audio, language=args.language, model_size=args.model,
                                  device=args.device, vad=False)
            log(f"segments: {len(segments)}")
        if not segments:
            print("error: transcription produced no segments. The recording may be too "
                  "quiet or too reverberant — try normalizing its loudness "
                  "(ffmpeg -af loudnorm) or a larger --model.", file=sys.stderr)
            return 1
    else:
        print("error: provide AUDIO or --segments", file=sys.stderr)
        return 2

    threshold = args.threshold
    if threshold is None:
        threshold = default_threshold(lyrics)
        log(f"match threshold: {threshold} "
            f"({'CJK' if threshold == CJK_THRESHOLD else 'alphabetic'} script)")

    aligned = align(segments, lyrics, pairing=args.pairing,
                    threshold=threshold, window=args.window,
                    karaoke=karaoke)
    if args.interpolate:
        aligned = interpolate_gaps(aligned)

    matched = sum(1 for a in aligned if a.matched)
    log(f"aligned {matched}/{len(aligned)} lines")

    # Name the gaps: the whole point of honest-gap semantics is that a human can
    # see exactly which lines need a look, so print them rather than a bare count.
    unmatched = [(i, a) for i, a in enumerate(aligned, 1) if not a.matched]
    if unmatched:
        filled = " (timestamps interpolated)" if args.interpolate else " (omitted from output)"
        log(f"unmatched{filled} — check these lines:")
        for i, a in unmatched:
            log(f"  line {i}: sim {a.score:.2f}  {a.line}")

    # A poor match rate almost always means the transcription was starved, not
    # that the lyrics are wrong — say so, because the cause is not guessable
    # from the output. (Only ASR runs can be diagnosed this way.)
    if not args.segments and matched < len(aligned) * 0.6:
        hints = []
        if args.vad:
            hints.append("--no-vad (the voice-activity filter silences slow singing)")
        if not args.separate:
            hints.append("--separate (a full mix hides the vocal from the ASR)")
        if hints:
            log(f"only {matched}/{len(aligned)} lines matched from {len(segments)} "
                f"segments — try " + ", or ".join(hints))

    return _write(args, fmt, targets, aligned, karaoke, log)


def _write(args, fmt, targets, aligned, karaoke, log) -> int:
    # TTML carries the language; the ASR language code is the one we know.
    lang = args.language or ""

    if fmt == "all":
        base = Path(args.output)
        base = base.with_name(base.name[:-len(base.suffix)] if base.suffix else base.name)
        for name in targets:
            path = base.with_name(base.name + EXTENSIONS[name])
            path.write_text(FORMATTERS[name](aligned, karaoke=karaoke, lang=lang))
            log(f"wrote {path}")
    elif args.output:
        Path(args.output).write_text(FORMATTERS[fmt](aligned, karaoke=karaoke, lang=lang))
        log(f"wrote {args.output}")
    else:
        sys.stdout.write(FORMATTERS[fmt](aligned, karaoke=karaoke, lang=lang))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
