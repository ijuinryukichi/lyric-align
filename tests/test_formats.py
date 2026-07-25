import json
import re

from lyric_align.charmap import char_timings, syllable_timings
from lyric_align.formats import (EXTENSIONS, FORMATTERS, to_aud, to_elrc, to_ttml,
                                 to_vtt)
from lyric_align.model import AlignedLine, Word

WORDS_EN = [Word(0.0, 0.5, "Amazing"), Word(0.5, 1.0, "grace")]
WORDS_JA = [Word(0.0, 0.5, "島の"), Word(0.5, 1.0, "左近")]


def en_line():
    line = "Amazing grace"
    return AlignedLine(line, 0.0, 1.0, 0.9, True, char_timings(line, WORDS_EN))


def ja_line():
    line = "島の左近"
    return AlignedLine(line, 0.0, 1.0, 0.9, True, char_timings(line, WORDS_JA))


def test_syllables_group_on_space_for_latin():
    units = syllable_timings("Amazing grace", char_timings("Amazing grace", WORDS_EN))
    assert [u["text"] for u in units] == ["Amazing", "grace"]
    assert units[0]["start"] == 0.0


def test_syllables_stay_per_character_for_cjk():
    # Japanese lyrics use spaces as phrasing, so splitting on them would give
    # useless chunks; per-character is what CJK karaoke formats expect.
    line = "硫黄が満ちる 道の奥"
    units = syllable_timings(line, char_timings(line, WORDS_JA))
    assert [u["text"] for u in units] == list("硫黄が満ちる道の奥")


def test_elrc_has_line_and_inline_timestamps():
    out = to_elrc([en_line()])
    assert out.startswith("[00:00.00]")
    assert "<00:00.00>Amazing" in out
    assert re.search(r"<\d\d:\d\d\.\d\d>grace", out)


def test_elrc_falls_back_to_plain_line_without_char_timings():
    out = to_elrc([AlignedLine("Amazing grace", 0.0, 1.0, 0.9, True, None)])
    assert out.strip() == "[00:00.00]Amazing grace"


def test_vtt_header_and_dotted_milliseconds():
    out = to_vtt([en_line()])
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in out


def test_aud_is_tab_separated_start_end_text():
    row = to_aud([en_line()]).strip().split("\t")
    assert row == ["0.000000", "1.000000", "Amazing grace"]


def test_ttml_wraps_syllables_in_spans_and_escapes():
    line = AlignedLine("rock & roll", 0.0, 1.0, 0.9, True,
                       char_timings("rock & roll", WORDS_EN))
    out = to_ttml([line])
    assert '<tt xmlns="http://www.w3.org/ns/ttml"' in out
    assert 'begin="00:00:00.000" end="00:00:01.000"' in out
    assert "&amp;" in out and "&" in out
    assert out.count("<span") >= 2


def _ttml_lines(xml: str) -> list[str]:
    """Rebuild each line from its spans the way a TTML consumer does."""
    out = []
    for inner in re.findall(r"<p [^>]*>(.*?)</p>", xml):
        out.append(re.sub(r"</?span[^>]*>", "", inner))
    return out


def _elrc_line(elrc: str) -> str:
    """Strip the line timestamp and the inline word timestamps from one eLRC line."""
    body = re.sub(r"^\[\d\d:\d\d\.\d\d\]", "", elrc.strip())
    return re.sub(r"<\d\d:\d\d\.\d\d>", "", body)


def test_ttml_and_elrc_rebuild_the_source_line_exactly():
    # A Japanese line carries a phrasing space *and* is one unit per character.
    # Deciding the separator from the line ("does it contain a space?") breaks
    # exactly here: it puts a space between every character and loses the real
    # one. The separator has to come from the source text, per unit.
    line = "硫黄が満ちる 道の奥"
    a = AlignedLine(line, 0.0, 1.0, 0.9, True, char_timings(line, WORDS_JA))
    assert _ttml_lines(to_ttml([a])) == [line]
    assert _elrc_line(to_elrc([a])) == line

    en = "Amazing grace"
    b = AlignedLine(en, 0.0, 1.0, 0.9, True, char_timings(en, WORDS_EN))
    assert _ttml_lines(to_ttml([b])) == [en]
    assert _elrc_line(to_elrc([b])) == en


def test_ttml_spans_stay_inside_their_line():
    # TTML requires a child's span to be contained by its parent's; a strict
    # player otherwise clamps or drops the tail.
    for a in (en_line(), ja_line()):
        xml = to_ttml([a])
        for p_begin, p_end, inner in re.findall(
                r'<p begin="([^"]+)" end="([^"]+)"[^>]*>(.*?)</p>', xml):
            spans = re.findall(r'begin="([^"]+)" end="([^"]+)"', inner)
            assert spans
            assert spans[0][0] >= p_begin
            assert spans[-1][1] <= p_end


def test_align_widens_a_line_to_contain_its_characters():
    # faster-whisper does not guarantee segment.end == last word end.
    from lyric_align.anchor import align
    from lyric_align.model import Segment
    seg = Segment(0.0, 1.0, "amazing grace",
                  [Word(0.0, 0.5, "amazing"), Word(0.5, 1.6, "grace")])
    a = align([seg], ["Amazing grace"], pairing=1, karaoke=True)[0]
    assert a.chars[-1]["end"] <= a.end
    assert a.chars[0]["start"] >= a.start


def test_ttml_declares_an_agent_and_the_language():
    out = to_ttml([en_line()], lang="en")
    assert '<ttm:agent type="person" xml:id="v1"/>' in out
    assert 'ttm:agent="v1"' in out
    assert 'xml:lang="en"' in out
    assert 'itunes:timing="Word"' in out


def test_ttml_language_comes_from_the_cli(tmp_path, capsys):
    from lyric_align.cli import main
    from pathlib import Path
    fix = Path(__file__).parent / "fixtures" / "segments_sample.json"
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n")
    out = tmp_path / "o.ttml"
    assert main([str(lyrics), "--segments", str(fix), "--pairing", "1",
                 "--language", "ja", "-f", "ttml", "-o", str(out)]) == 0
    assert 'xml:lang="ja"' in out.read_text()
    capsys.readouterr()


def test_unmatched_lines_are_absent_from_every_text_format():
    lines = [en_line(), AlignedLine("dropped line", None, None, 0.1, False, None)]
    for name, fmt in FORMATTERS.items():
        out = fmt(lines, karaoke=True)
        if name == "json":
            assert any(d["line"] == "dropped line" for d in json.loads(out))
        else:
            assert "dropped line" not in out


def test_every_format_has_an_extension():
    assert set(EXTENSIONS) == set(FORMATTERS)


def test_cli_writes_every_format_with_f_all(tmp_path, capsys):
    from lyric_align.cli import main
    from pathlib import Path
    fix = Path(__file__).parent / "fixtures" / "segments_sample.json"
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n標野ゆき野守は見ずや\n君が袖振る\n")
    rc = main([str(lyrics), "--segments", str(fix), "--pairing", "1",
               "-f", "all", "-o", str(tmp_path / "out")])
    assert rc == 0
    for ext in EXTENSIONS.values():
        assert (tmp_path / f"out{ext}").exists(), ext
    # elrc/ttml are per-syllable formats: they must get char timings even though
    # --karaoke was not passed.
    assert "<00:00.50>" in (tmp_path / "out.elrc").read_text()
    capsys.readouterr()


def test_cli_rejects_f_all_without_output(tmp_path, capsys):
    from lyric_align.cli import main
    from pathlib import Path
    fix = Path(__file__).parent / "fixtures" / "segments_sample.json"
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n")
    assert main([str(lyrics), "--segments", str(fix), "-f", "all"]) == 2
    assert "needs -o" in capsys.readouterr().err
