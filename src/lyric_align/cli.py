"""Command-line interface.

    lyric-align AUDIO LYRICS.txt -o out.lrc          # transcribe + align
    lyric-align --segments segs.json LYRICS.txt -f ass --karaoke

LYRICS is a plain-text file, one lyric line per line; blank lines are ignored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .anchor import align, interpolate_gaps
from .formats import FORMATTERS
from .model import Segment


def read_lyrics(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


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
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    lyrics = read_lyrics(Path(args.lyrics))

    if args.segments:
        segments = load_segments(Path(args.segments))
    elif args.audio:
        from .asr import transcribe
        segments = transcribe(args.audio, language=args.language,
                              model_size=args.model, device=args.device)
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
    print(f"aligned {matched}/{len(aligned)} lines", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
