"""Command-line interface.

    lyric-align AUDIO LYRICS.txt -o out.lrc          # transcribe + align
    lyric-align AUDIO LYRICS.txt --separate -o o.lrc  # split vocals first (better)
    lyric-align --segments segs.json LYRICS.txt -f ass --karaoke

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
from .formats import FORMATTERS
from .model import Segment

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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lyric-align", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", nargs="?", help="audio file (omit if --segments given)")
    p.add_argument("lyrics", help="plain-text lyrics, one line per line")
    p.add_argument("-o", "--output", help="output path (default: stdout)")
    p.add_argument("-f", "--format", default=None,
                   choices=sorted(FORMATTERS), help="output format (default: infer from -o, else json)")
    p.add_argument("--segments", help="pre-computed segments JSON (skip ASR)")
    p.add_argument("--separate", action="store_true",
                   help="split the vocal stem with Demucs first (needs [separate]); "
                        "slow but clearly more accurate on a full mix")
    p.add_argument("--pairing", type=int, default=2,
                   help="lyric lines per stanza unit (default 2; use 1 if ASR splits per line)")
    p.add_argument("--threshold", type=float, default=0.25)
    p.add_argument("--window", type=int, default=4)
    p.add_argument("--karaoke", action="store_true", help="per-character timings (ass/json)")
    p.add_argument("--interpolate", action="store_true",
                   help="fill unmatched lines by interpolation")
    p.add_argument("--language", default="ja")
    p.add_argument("--model", default="medium", help="faster-whisper model size")
    p.add_argument("--device", default="cpu")
    p.add_argument("--no-vad", dest="vad", action="store_false",
                   help="disable the ASR voice-activity filter. The filter helps on dense "
                        "delivery (rap) but silences slow, sustained singing — if you get "
                        "few or no segments, try this first")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress reporting")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    for label, path in (("lyrics", args.lyrics), ("audio", args.audio),
                        ("segments", args.segments)):
        if path and not Path(path).exists():
            print(f"error: {label} file not found: {path}", file=sys.stderr)
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

    aligned = align(segments, lyrics, pairing=args.pairing,
                    threshold=args.threshold, window=args.window,
                    karaoke=args.karaoke)
    if args.interpolate:
        aligned = interpolate_gaps(aligned)

    fmt = args.format
    if fmt is None and args.output:
        fmt = Path(args.output).suffix.lstrip(".").lower()
    if fmt not in FORMATTERS:
        fmt = "json"
    text = FORMATTERS[fmt](aligned, karaoke=args.karaoke)

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

    if args.output:
        Path(args.output).write_text(text)
        log(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
