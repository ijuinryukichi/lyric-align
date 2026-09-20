import json
from pathlib import Path

from lyric_align.model import Segment, Word

FIX = Path(__file__).parent / "fixtures" / "segments_sample.json"


def test_segment_round_trips_through_dicts():
    # to_dict is the mirror of from_dict: what --dump-segments writes has to be
    # what --segments reads, or the cache silently degrades the next run.
    original = [Segment.from_dict(d) for d in json.loads(FIX.read_text())]
    back = [Segment.from_dict(s.to_dict()) for s in original]
    assert back == original


def test_segment_to_dict_keeps_word_timings():
    # The reason to keep a segments file at all. `-f json` output does not carry
    # these, so dropping them here would make the dump useless for karaoke.
    seg = Segment(0.5, 1.5, "ゆき", [Word(0.5, 0.9, "ゆ"), Word(0.9, 1.5, "き")])
    assert seg.to_dict()["words"] == [
        {"start": 0.5, "end": 0.9, "word": "ゆ"},
        {"start": 0.9, "end": 1.5, "word": "き"},
    ]


def test_segment_to_dict_always_carries_a_words_key():
    # Backends without word timing still produce a file --segments can read.
    assert Segment(0.0, 1.0, "text").to_dict()["words"] == []
