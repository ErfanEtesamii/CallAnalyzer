from scripts.benchmark_stt import cer, wer
def test_wer_cer():
    assert wer("سلام وقت بخیر", "سلام وقت بخیر") == 0
    assert round(wer("a b c d", "a b x d"), 2) == 0.25
    assert cer("ab", "ac") == 0.5
