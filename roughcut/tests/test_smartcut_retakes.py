from smartcut.retakes import detect_retakes
from smartcut.schema import Word


def test_retakes_keep_the_last_near_duplicate_sentence():
    words = [
        Word(0, .2, "Vamos"), Word(.2, .4, "embora."),
        Word(1, 1.2, "Vamos"), Word(1.2, 1.4, "embora!"),
    ]
    retakes = detect_retakes(words)
    assert len(retakes) == 1
    assert retakes[0]["start_s"] == 0
    assert retakes[0]["kept_take_start_s"] == 1
