from lyric_align.normalize import (CJK_THRESHOLD, LATIN_THRESHOLD, cjk_ratio,
                                   default_threshold, nchars, normalize, similarity)


def test_default_threshold_is_script_aware():
    assert default_threshold(["治部少輔に過ぎたるものが二つ在り"]) == CJK_THRESHOLD
    assert default_threshold(["Amazing grace, how sweet the sound"]) == LATIN_THRESHOLD
    # numerals and latin mixed into Japanese must not flip the script decision
    assert default_threshold(["3.26 夜明け前 中将自ら 刀"]) == CJK_THRESHOLD


def test_latin_default_rejects_chance_similarity():
    # Two unrelated English lines score 0.34 — above the CJK floor, below the
    # latin one. This is exactly the false match the split default prevents.
    sim = similarity("Through many dangers, toils and snares",
                     "We've no less days to sing God's praise")
    assert CJK_THRESHOLD < sim < LATIN_THRESHOLD


def test_cjk_ratio_extremes():
    assert cjk_ratio("あいう漢字カタカナ") == 1.0
    assert cjk_ratio("abc def") == 0.0
    assert cjk_ratio("") == 0.0


def test_normalize_strips_space_and_punct():
    assert normalize("あかね さす、紫野") == "あかねさす紫野"
    assert normalize("「かかれぃ！」") == "かかれぃ"


def test_similarity_identical():
    assert similarity("島の左近", "島の左近") == 1.0


def test_similarity_tolerates_asr_error():
    # ASR misheard 佐和山 → 沢山 but timing should still match
    s = similarity("島の左近と佐和山の城", "島の左近と沢山の城")
    assert 0.7 < s < 1.0


def test_similarity_ignores_punctuation():
    assert similarity("君が袖振る", "君が、袖振る。") == 1.0


def test_nchars_excludes_spaces():
    assert nchars("島の左近 佐和山") == 7
