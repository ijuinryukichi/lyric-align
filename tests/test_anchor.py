import json
from pathlib import Path

from lyric_align import align, interpolate_gaps
from lyric_align.breath import split_words_by_breath
from lyric_align.charmap import char_timings
from lyric_align.model import Segment, Word

FIX = Path(__file__).parent / "fixtures" / "segments_sample.json"


def load():
    return [Segment.from_dict(d) for d in json.loads(FIX.read_text())]


def test_align_per_line():
    segs = load()
    lyrics = ["あかねさす紫野ゆき", "標野ゆき野守は見ずや", "君が袖振る"]
    out = align(segs, lyrics, pairing=1)
    assert [a.matched for a in out] == [True, True, True]
    assert out[0].start == 0.50
    assert out[2].line == "君が袖振る"


def test_align_stanza_pairing_breath_split():
    # two lyric lines merged into one ASR segment → breath split recovers each
    words = [Word(0.0, 0.4, "あ"), Word(0.4, 0.8, "い"),
             Word(1.5, 1.9, "う"), Word(1.9, 2.3, "え")]  # big gap at index 2
    seg = Segment(0.0, 2.3, "あいうえ", words)
    out = align([seg], ["あい", "うえ"], pairing=2, threshold=0.1)
    assert len(out) == 2
    assert out[0].matched and out[1].matched
    assert out[0].start == 0.0 and out[0].end == 0.8
    assert out[1].start == 1.5 and out[1].end == 2.3


def test_unmatched_line_is_honest():
    segs = load()
    lyrics = ["あかねさす紫野ゆき", "全く違う歌詞ここにある"]
    out = align(segs, lyrics, pairing=1, window=1)
    assert out[0].matched is True
    assert out[1].matched is False
    assert out[1].start is None


def test_interpolate_fills_gaps():
    segs = load()
    lyrics = ["あかねさす紫野ゆき", "全く違う歌詞ここにある", "君が袖振る"]
    out = interpolate_gaps(align(segs, lyrics, pairing=1))
    assert out[1].start is not None
    assert out[1].matched is False  # still flagged as guessed


def test_breath_split_respects_line_count():
    words = [Word(i * 1.0, i * 1.0 + 0.5, "x") for i in range(6)]
    groups = split_words_by_breath(words, ["ab", "cd", "ef"])
    assert len(groups) == 3
    assert sum(len(g) for g in groups) == 6


def test_char_timings_skips_spaces():
    words = [Word(0.0, 1.0, "ab"), Word(1.0, 2.0, "cd")]
    ct = char_timings("a b", words)
    assert [c["char"] for c in ct] == ["a", "b"]


def test_char_timings_are_strictly_positive_and_ordered():
    # Many characters over a short span is where proportional interpolation plus
    # millisecond rounding used to collapse a syllable to zero length.
    words = [Word(10.0, 10.06, "ab"), Word(10.06, 10.12, "cd")]
    ct = char_timings("島の左近と佐和山の城なり", words)
    assert all(c["end"] > c["start"] for c in ct)
    assert all(b["start"] >= a["end"] for a, b in zip(ct, ct[1:]))
