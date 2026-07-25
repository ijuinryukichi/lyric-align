"""lyric-align — place known lyrics on an audio timeline.

You already have the correct lyrics; you only need the *times*. lyric-align
anchors known lyric lines onto ASR word timings via character-level fuzzy
matching — built for space-less languages (Japanese, Chinese) and sung vocals
(including rap), where whitespace tokenization and forced aligners fall short.
"""
from .anchor import align, interpolate_gaps
from .model import AlignedLine, Segment, Word
from .normalize import normalize, similarity

__version__ = "0.3.0"

__all__ = [
    "align", "interpolate_gaps",
    "AlignedLine", "Segment", "Word",
    "normalize", "similarity",
    "__version__",
]
