from pathlib import Path

from analysis import speech
from core.schema import Word


def _result(*rows):
    return {"segments": [{"words": [{"word": text, "start": start, "end": end, "probability": .9} for text, start, end in rows]}]}


def test_words_apply_glossary_and_skip_untimed():
    result = _result((" eindoven,", 0, .5), (" bah", .6, .9))
    result["segments"][0]["words"].append({"word": "sem", "start": None, "end": 1})
    words = speech.words_from_result(result, {"eindoven": "Eindhoven"})
    assert [word.text for word in words] == ["Eindhoven,", "bah"]


def test_sentences_split_on_punctuation_pause_and_length():
    words = [Word(0, .4, "Hoje"), Word(.5, 1, "chegamos."), Word(1.1, 1.5, "Depois"), Word(3, 3.4, "parque")]
    sentences = speech.group_sentences(words)
    assert [sentence.text for sentence in sentences] == ["Hoje chegamos.", "Depois", "parque"]
    long = [Word(index, index + .9, "palavra") for index in range(25)]
    assert all(sentence.end_s - sentence.start_s <= speech.MAX_SENTENCE_S + 1 for sentence in speech.group_sentences(long))


def test_transcribe_take_uses_cache(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.mp4"
    source.write_bytes(b"x")
    calls = []

    def fake(audio, model):
        calls.append(model)
        return _result(("É", 0, .2), ("nessas", .3, .6), ("coisas.", .7, 1))

    monkeypatch.setattr(speech, "transcribe_audio", fake)
    first = speech.transcribe_take("T01", source, source, tmp_path / ".cache", model="tiny")
    second = speech.transcribe_take("T09", source, source, tmp_path / ".cache", model="tiny")
    assert calls == ["tiny"]
    assert second.take_id == "T09"
    assert second.sentences[0].text == first.sentences[0].text == "É nessas coisas."
    speech.transcribe_take("T01", source, source, tmp_path / ".cache", model="other")
    assert calls == ["tiny", "other"]


def test_release_model_is_safe_without_loaded_model():
    speech.release_model()


def test_low_confidence_segments_are_treated_as_hallucination():
    real = {"words": [{"word": "Hoje", "start": 0, "end": .4, "probability": .97}, {"word": "pra", "start": .5, "end": .7, "probability": .35},
                      {"word": "costa.", "start": .8, "end": 1.2, "probability": .97}]}
    noise = {"words": [{"word": "images", "start": 3, "end": 3.5, "probability": .0}, {"word": "de", "start": 3.6, "end": 3.8, "probability": .08}]}
    words = speech.words_from_result({"segments": [real, noise]}, {})
    assert [word.text for word in words] == ["Hoje", "pra", "costa."]
