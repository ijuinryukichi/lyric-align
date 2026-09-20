import json
import sys
import types
from pathlib import Path

import pytest

from lyric_align.cli import main, read_lyrics
from lyric_align.model import Segment

FIX = Path(__file__).parent / "fixtures" / "segments_sample.json"


def write_lyrics(tmp_path, text):
    p = tmp_path / "lyrics.txt"
    p.write_text(text)
    return p


def test_read_lyrics_skips_markers_comments_blanks(tmp_path):
    p = write_lyrics(tmp_path, "\n".join([
        "[Verse 1]", "", "あかねさす紫野ゆき", "# a note",
        "(Hook)", "標野ゆき野守は見ずや", "   ",
    ]))
    assert read_lyrics(p) == ["あかねさす紫野ゆき", "標野ゆき野守は見ずや"]


def test_read_lyrics_keeps_bracketed_lyric_content(tmp_path):
    # A bracketed *lyric* (quotes, shouts) must survive; only bare section
    # markers are dropped, so length is the discriminator we rely on.
    p = write_lyrics(tmp_path, "「かかれぃ！」と鬼が吼え\n[Hook]\n")
    assert read_lyrics(p) == ["「かかれぃ！」と鬼が吼え"]


def test_cli_segments_to_lrc(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, "あかねさす紫野ゆき\n標野ゆき野守は見ずや\n君が袖振る\n")
    out = tmp_path / "out.lrc"
    rc = main([str(lyrics), "--segments", str(FIX), "--pairing", "1", "-o", str(out)])
    assert rc == 0
    text = out.read_text()
    assert text.startswith("[00:00.50]")
    assert "君が袖振る" in text
    assert "aligned 3/3 lines" in capsys.readouterr().err


def test_cli_names_unmatched_lines(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, "あかねさす紫野ゆき\n全く違う歌詞ここにある\n")
    rc = main([str(lyrics), "--segments", str(FIX), "--pairing", "1",
               "--window", "1", "-f", "json"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "unmatched" in err
    assert "全く違う歌詞ここにある" in err  # the human is told *which* line to check


def test_cli_quiet_silences_progress(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, "あかねさす紫野ゆき\n")
    main([str(lyrics), "--segments", str(FIX), "--pairing", "1", "-q", "-f", "json"])
    cap = capsys.readouterr()
    assert cap.err == ""
    assert json.loads(cap.out)[0]["line"] == "あかねさす紫野ゆき"


def test_cli_reports_missing_files_without_traceback(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, "あかねさす紫野ゆき\n")
    assert main([str(tmp_path / "nope.mp3"), str(lyrics)]) == 2
    assert "audio file not found" in capsys.readouterr().err
    assert main([str(lyrics), "--segments", str(tmp_path / "nope.json")]) == 2
    assert "segments file not found" in capsys.readouterr().err


def test_cli_rejects_empty_lyrics(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, "[Verse 1]\n\n")
    assert main([str(lyrics), "--segments", str(FIX)]) == 2
    assert "no lyric lines" in capsys.readouterr().err


def test_cli_reports_the_pairing_it_picked(tmp_path, capsys):
    from lyric_align.cli import main
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n標野ゆき野守は見ずや\n")
    assert main([str(lyrics), "--segments", str(FIX), "-o", str(tmp_path / "o.json")]) == 0
    err = capsys.readouterr().err
    assert "pairing:" in err and "auto" in err


def test_cli_accepts_an_explicit_pairing(tmp_path, capsys):
    from lyric_align.cli import main
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n")
    assert main([str(lyrics), "--segments", str(FIX), "--pairing", "1",
                 "-o", str(tmp_path / "o.json")]) == 0
    assert "auto" not in capsys.readouterr().err


def test_cli_rejects_a_nonsense_pairing(tmp_path, capsys):
    import pytest

    from lyric_align.cli import main
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("あかねさす紫野ゆき\n")
    with pytest.raises(SystemExit):
        main([str(lyrics), "--segments", str(FIX), "--pairing", "two",
              "-o", str(tmp_path / "o.json")])
    capsys.readouterr()


def fake_asr(monkeypatch, segments):
    """Stand in for faster-whisper so the CLI's ASR path is testable offline.

    The CLI does `from .asr import transcribe`, so pre-seeding sys.modules is
    enough — nothing heavy is ever imported.
    """
    mod = types.ModuleType("lyric_align.asr")
    mod.transcribe = lambda *a, **k: list(segments)
    monkeypatch.setitem(sys.modules, "lyric_align.asr", mod)


def fixture_segments():
    return [Segment.from_dict(d) for d in json.loads(FIX.read_text())]


LYRICS_3 = "あかねさす紫野ゆき\n標野ゆき野守は見ずや\n君が袖振る\n"


def test_cli_dumped_segments_reproduce_the_same_alignment(tmp_path, monkeypatch):
    # The whole point of the flag: a second run off the dump must land exactly
    # where the transcribing run did, or the cache is not a cache.
    fake_asr(monkeypatch, fixture_segments())
    lyrics = write_lyrics(tmp_path, LYRICS_3)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    dumped = tmp_path / "segs.json"

    first = tmp_path / "first.lrc"
    rc = main([str(audio), str(lyrics), "--pairing", "1", "-q",
               "--dump-segments", str(dumped), "-o", str(first)])
    assert rc == 0
    assert dumped.exists()

    second = tmp_path / "second.lrc"
    rc = main([str(lyrics), "--segments", str(dumped), "--pairing", "1", "-q",
               "-o", str(second)])
    assert rc == 0
    assert second.read_text() == first.read_text()


def test_cli_dumps_before_aligning_so_a_crash_cannot_cost_the_audio_half(
        tmp_path, monkeypatch):
    # The expensive half is the transcription. If the run dies in the cheap
    # half, the dump must already be on disk — that is the whole ordering
    # claim, so break the cheap half on purpose and check the file survives.
    fake_asr(monkeypatch, fixture_segments())

    def explode(*a, **k):
        raise RuntimeError("alignment blew up")

    monkeypatch.setattr("lyric_align.cli.align", explode)
    lyrics = write_lyrics(tmp_path, LYRICS_3)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    dumped = tmp_path / "segs.json"

    with pytest.raises(RuntimeError):
        main([str(audio), str(lyrics), "--pairing", "1", "-q", "-f", "json",
              "--dump-segments", str(dumped)])

    assert [s["text"] for s in json.loads(dumped.read_text())] == \
        [s.text for s in fixture_segments()]


def test_cli_dumped_segments_keep_word_timings(tmp_path, monkeypatch):
    # `-f json` emits aligned lines, which carry no word timings — the dump has
    # to, or karaoke output degrades on the second run.
    fake_asr(monkeypatch, fixture_segments())
    lyrics = write_lyrics(tmp_path, LYRICS_3)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    dumped = tmp_path / "segs.json"
    main([str(audio), str(lyrics), "--pairing", "1", "-q", "-f", "json",
          "--dump-segments", str(dumped)])

    got = json.loads(dumped.read_text())
    assert got[0]["words"][0] == {"start": 0.5, "end": 0.9, "word": "あか"}
    assert all(s["words"] for s in got)


def test_dumped_segments_stay_one_line_per_segment(tmp_path, monkeypatch):
    # Word timings nested under a plain indent run to hundreds of lines per
    # song. The brackets are written by hand to keep that readable, so this
    # pins both halves: still valid JSON, still one line you can eyeball.
    fake_asr(monkeypatch, fixture_segments())
    lyrics = write_lyrics(tmp_path, LYRICS_3)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"")
    dumped = tmp_path / "segs.json"
    main([str(audio), str(lyrics), "--pairing", "1", "-q", "-f", "json",
          "--dump-segments", str(dumped)])

    text = dumped.read_text()
    assert json.loads(text)
    assert text.splitlines()[0] == "["
    assert text.splitlines()[-1] == "]"
    assert len(text.splitlines()) == len(fixture_segments()) + 2


def test_cli_dump_segments_is_a_noop_when_segments_were_given(tmp_path, capsys):
    lyrics = write_lyrics(tmp_path, LYRICS_3)
    dumped = tmp_path / "segs.json"
    rc = main([str(lyrics), "--segments", str(FIX), "--pairing", "1",
               "-f", "json", "--dump-segments", str(dumped)])
    assert rc == 0
    assert not dumped.exists()
    assert "--dump-segments ignored" in capsys.readouterr().err
