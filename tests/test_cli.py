import json
from pathlib import Path

from lyric_align.cli import main, read_lyrics

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
