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


# Hiragana, katakana, CJK ideographs (incl. extension A and compatibility) and
# half-width katakana. Enough to tell "large character inventory" scripts apart
# from alphabetic ones, which is all the threshold heuristic needs.
_CJK = re.compile(r'[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]')

CJK_THRESHOLD = 0.25
LATIN_THRESHOLD = 0.50


def cjk_ratio(text: str) -> float:
    """Fraction of significant characters that are Japanese/Chinese."""
    chars = normalize(text)
    if not chars:
        return 0.0
    return len(_CJK.findall(chars)) / len(chars)


def default_threshold(lyrics: list[str] | str) -> float:
    """Pick a match threshold from the script the lyrics are written in.

    A single similarity floor cannot serve both scripts, because chance
    similarity depends on how many characters the language has to choose from.
    Measured on real data:

    - Japanese: unrelated lines score low, while *true* matches against error-prone
      sung ASR drop as far as 0.26 — the floor has to stay low (0.25) or genuine
      lines are discarded.
    - Latin script: 26 letters plus shared vowels mean two completely unrelated
      English sentences score 0.28-0.34, i.e. above that same floor. A 0.25
      threshold silently invents matches; 0.50 leaves room above the noise.
    """
    text = "\n".join(lyrics) if not isinstance(lyrics, str) else lyrics
    return CJK_THRESHOLD if cjk_ratio(text) >= 0.2 else LATIN_THRESHOLD
