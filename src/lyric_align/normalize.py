"""Character-level normalization and similarity for space-less languages (CJK-first).

The core insight of lyric-align: word alignment tools split on whitespace, which
does not exist in Japanese/Chinese. We compare *characters* instead, so ASR
transcription errors (wrong kanji, dropped particles) degrade the score
gracefully without breaking the match entirely.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# Punctuation / whitespace stripped before comparison. Extend per language.
_STRIP = re.compile(r'[\s「」『』、。！？!?・,.\-—…]+')


def normalize(s: str) -> str:
    """Strip whitespace and punctuation for fuzzy character comparison."""
    return _STRIP.sub('', s)


def similarity(a: str, b: str) -> float:
    """Character-level similarity in [0, 1].

    Uses difflib.SequenceMatcher on normalized strings — no language model,
    no dependencies. Robust to ASR errors because a few wrong characters only
    shave the ratio rather than zeroing it.
    """
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def nchars(s: str) -> int:
    """Count of significant (non-space) characters."""
    return len(s.replace(' ', ''))
