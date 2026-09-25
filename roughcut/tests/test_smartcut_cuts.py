from smartcut.config import load_rules
from smartcut.cuts import cuts_from_words
from smartcut.schema import SpeechRegion, Word


def test_cuts_only_between_words_and_keeps_breath_inside_sentence():
    words = [Word(0, 1, "Eu"), Word(2.2, 3, "acho"), Word(3.1, 4, "sim")]
    cuts = cuts_from_words(words, load_rules("colab"))
    assert len(cuts) == 1
    assert cuts[0].reason == "pausa_na_frase"
    assert cuts[0].start_s > words[0].end_s
    assert cuts[0].end_s < words[1].start_s


def test_sentence_pause_keeps_the_longer_editorial_pause():
    words = [Word(0, 1, "Pronto."), Word(3, 4, "Seguimos")]
    cut = cuts_from_words(words, load_rules("colab"))[0]
    assert cut.reason == "fim_de_frase"
    assert round((3 - 1) - (cut.end_s - cut.start_s), 2) == 0.35


def test_protected_pause_is_never_cut():
    words = [Word(0, 1, "Pronto."), Word(3, 4, "Seguimos")]
    assert cuts_from_words(words, load_rules("colab"), [SpeechRegion(1.1, 2.9)]) == []
