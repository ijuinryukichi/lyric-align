import json
from pathlib import Path

from lyric_align import align, interpolate_gaps
from lyric_align.breath import split_words_by_breath
from lyric_align.charmap import char_timings
from lyric_align.model import Segment, Word
from lyric_align.normalize import similarity

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


def test_a_reachable_segment_below_the_threshold_stays_unmatched():
    # The test above withholds the segment (window=1), so it exercises the
    # forward window, not the threshold. This one puts a candidate squarely in
    # reach and relies on the score alone to reject it — the honest-gap contract
    # is what keeps this line empty, and nothing else.
    seg = Segment(0.0, 3.0, "全然別のことを喋っている")
    out = align([seg], ["君が袖振る"], pairing=1)
    assert out[0].matched is False
    assert out[0].start is None and out[0].end is None


def test_the_cjk_floor_still_accepts_a_badly_heard_true_match():
    # Real ASR output for a real line, and the reason the CJK floor sits at 0.25:
    # a *correct* match on sung Japanese can score as low as 0.26. The model got
    # the moment right (朝霧開戦 is there, 九月十五 became "9月15") and still only
    # clears the floor by a hair. Raise the floor and this true match is lost.
    unit = "九月十五朝霧開戦黒田細川矢刃交わし合戦"
    heard = "9月15 朝霧開戦 来るだ 遅かえば 可視化せん"
    assert 0.25 < similarity(unit, heard) < 0.30

    seg = Segment(0.0, 6.0, heard)
    out = align([seg], ["九月十五朝霧開戦", "黒田細川矢刃交わし合戦"], pairing=2)
    assert [a.matched for a in out] == [True, True]


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


def test_auto_pairing_reads_the_asr_segmentation():
    # pairing is a property of the ASR's segmentation, not of the song: it is
    # how many lyric lines the model merged into one segment.
    from lyric_align import auto_pairing
    segs = [Segment(float(i), i + 1.0, "x") for i in range(10)]
    assert auto_pairing(["l"] * 20, segs) == 2   # medium-like: ~2 lines/segment
    assert auto_pairing(["l"] * 11, segs) == 1   # large-v3-like: ~1 line/segment


def test_auto_pairing_is_capped_and_safe_when_the_asr_collapses():
    # A full mix makes Whisper merge whole verses; the answer there is to
    # separate the vocal, not to widen the unit, so the estimate stops at 3.
    from lyric_align.anchor import AUTO_PAIRING_MAX, auto_pairing
    segs = [Segment(0.0, 200.0, "x")] * 3
    assert auto_pairing(["l"] * 76, segs) == AUTO_PAIRING_MAX
    assert auto_pairing(["l"] * 10, []) == 1     # no segments: never divide by zero


def test_align_defaults_to_auto_pairing():
    from lyric_align import auto_pairing
    segs = load()
    lyrics = ["あかねさす紫野ゆき", "標野ゆき野守は見ずや", "君が袖振る"]
    chosen = auto_pairing(lyrics, segs)
    assert [a.to_dict() for a in align(segs, lyrics)] == \
           [a.to_dict() for a in align(segs, lyrics, pairing=chosen)]


def test_align_rejects_an_unknown_pairing_keyword():
    import pytest
    with pytest.raises(ValueError, match="auto"):
        align(load(), ["あかねさす紫野ゆき"], pairing="whatever")
