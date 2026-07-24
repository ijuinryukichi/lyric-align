"""Shared data types. Plain dataclasses so any ASR backend can feed the aligner."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    start: float
    end: float
    word: str


@dataclass
class Segment:
    """One ASR segment. `words` may be empty if the backend lacks word timing."""
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(
            start=float(d["start"]),
            end=float(d["end"]),
            text=d.get("text", "").strip(),
            words=[Word(float(w["start"]), float(w["end"]), w["word"])
                   for w in d.get("words", []) if w.get("start") is not None],
        )


@dataclass
class AlignedLine:
    """A known lyric line placed on the timeline.

    matched=False means the aligner could not confidently place this line
    (score below threshold). We surface it honestly rather than inventing a
    timestamp — the caller can fill gaps by interpolation or manual review.
    """
    line: str
    start: float | None
    end: float | None
    score: float
    matched: bool
    chars: list[dict] | None = None  # optional per-char timings (karaoke)

    def to_dict(self) -> dict:
        d = {"line": self.line, "start": self.start, "end": self.end,
             "score": round(self.score, 3), "matched": self.matched}
        if self.chars is not None:
            d["chars"] = self.chars
        return d
