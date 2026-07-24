from lyric_align.normalize import nchars, normalize, similarity


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
