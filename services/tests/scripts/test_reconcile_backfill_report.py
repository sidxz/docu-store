from scripts.reconcile_compound_labels import classify_change


def test_classify_single_glyph_swap():
    assert classify_change("CMX41O", "CMX410") == "O->0"


def test_classify_ignores_hyphen_and_case_formatting():
    assert classify_change("gsk-286", "GSK286") == "identical"


def test_classify_length_mismatch():
    assert classify_change("CMX41", "CMX410") == "format/length"
