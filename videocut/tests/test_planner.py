"""Planejador em etapas: base cronológica, capítulos e blocos por capítulo."""
import json
from pathlib import Path

from analysis.inventory import build_inventory
from analysis.speech import group_sentences
from core.schema import Take, Transcript, VisualObservation, Word
from story import planner
from story.chronology import base_cut, chronological, is_retake, recorded_at


def _speech(take_id: str, *phrases: tuple[float, str]) -> Transcript:
    words = []
    for start, text in phrases:
        words += [Word(round(start + i * .4, 2), round(start + i * .4 + .3, 2), token) for i, token in enumerate(text.split())]
    return Transcript(take_id, words=words, sentences=group_sentences(words))


def day_inventory():
    """Quatro takes DJI fora de ordem alfabética de gravação, com repetição e ruído."""
    takes = [
        Take("T01", "/raw/DJI_20260927150000_0003_D.MP4", "DJI_20260927150000_0003_D.MP4", 40),
        Take("T02", "/raw/DJI_20260927133000_0001_D.MP4", "DJI_20260927133000_0001_D.MP4", 40),
        Take("T03", "/raw/DJI_20260927140000_0002_D.MP4", "DJI_20260927140000_0002_D.MP4", 40),
        Take("T04", "/raw/DJI_20260927160000_0004_D.MP4", "DJI_20260927160000_0004_D.MP4", 40),
    ]
    transcripts = {
        "T02": _speech("T02", (1, "Bom dia, hoje a gente vai no IKEA comprar a estante."),
                       (10, "Bom dia, hoje a gente vai no IKEA comprar a estante nova.")),
        "T03": _speech("T03", (2, "Chegamos, olha o tamanho desse lugar, é enorme mesmo."), (20, "capá.")),
        "T01": _speech("T01", (3, "Achamos a estante e ainda comemos as almôndegas famosas.")),
        "T04": _speech("T04", (5, "Montamos tudo e ficou do jeito que a gente queria.")),
    }
    observations = {
        "T03": [VisualObservation("T03", 25, 40, "corredor da loja", action="família caminha pelos corredores", interest=.7)],
        "T04": [VisualObservation("T04", 20, 40, "estante montada", action="criança coloca livros", interest=.8)],
    }
    return build_inventory(takes, transcripts, observations)


class Scripted:
    """Responde capítulos e blocos como um modelo local faria, contando as chamadas."""

    name = "roteiro"

    def __init__(self, outline, chapters=None):
        self.outline, self.chapters, self.calls = outline, chapters or {}, []

    def generate(self, prompt, images=None, max_tokens=700):
        self.calls.append(prompt)
        if "Primeiro passo" in prompt:
            return json.dumps(self.outline)
        number = int(prompt.split("Capítulo ")[1].split(" de ")[0])
        return json.dumps(self.chapters.get(number, {"blocos": []}))

    def release(self):
        pass


def test_takes_follow_camera_recording_time():
    inventory = day_inventory()
    assert [take.id for take in chronological(inventory.takes)] == ["T02", "T03", "T01", "T04"]
    assert recorded_at(inventory.takes[1]).hour == 13


def test_base_cut_drops_noise_and_keeps_the_last_retake():
    cut = base_cut(day_inventory())
    texts = [moment.speech for moment in cut.speech]
    assert not any("capá" in text for text in texts)
    assert any("estante nova" in text for text in texts) and len(cut.retakes) == 1
    assert [moment.take_id for moment in cut.speech] == ["T02", "T03", "T01", "T04"]


def test_retake_detection_needs_similar_speech():
    first, again = base_cut(day_inventory()).retakes[0], base_cut(day_inventory()).speech[0]
    assert is_retake(first, again)


def test_missing_takes_stay_with_the_chapter_before_them():
    chapters = planner.normalize_chapters({"capitulos": [{"titulo": "Manhã", "takes": ["T02"]}, {"titulo": "Casa", "takes": ["T04", "T99"]}]},
                                          day_inventory())
    assert [chapter["takes"] for chapter in chapters] == [["T02", "T03", "T01"], ["T04"]]
    assert planner.normalize_chapters({}, day_inventory())[0]["titulo"] == "Parte 1"


def test_omitted_speech_comes_back_and_explicit_discards_are_respected():
    inventory = day_inventory()
    cut = base_cut(inventory)
    moments = planner.chapter_moments(cut, ["T02", "T03"])
    speech = [moment.id for moment in moments if moment.kind == "fala"]
    blocks = planner.chapter_blocks({"blocos": [{"momento": speech[1], "papel": "contexto"}, {"momento": "T99.01"}], "descartados": []},
                                    moments, cut)
    assert [block["momento"] for block in blocks] == speech
    dropped = planner.chapter_blocks({"blocos": [], "descartados": [speech[0]]}, moments, cut)
    assert [block["momento"] for block in dropped] == speech[1:]


def test_long_speech_gets_broll_when_the_model_forgets():
    inventory = day_inventory()
    cut = base_cut(inventory)
    moments = planner.chapter_moments(cut, ["T02", "T03"])
    long_speech = next(moment for moment in moments if moment.kind == "fala" and moment.take_id == "T02")
    long_speech.end_s = long_speech.start_s + 12
    blocks = planner.chapter_blocks({"blocos": [{"momento": long_speech.id}]}, moments, cut)
    first = next(block for block in blocks if block["momento"] == long_speech.id)
    assert first["apoio"] and first["apoio"][0]["momento"].startswith("T03")


def test_plan_uses_every_useful_speech_with_hook_first_and_caches(tmp_path: Path):
    inventory = day_inventory()
    hook = next(moment.id for moment in base_cut(inventory).speech if moment.take_id == "T01")
    outline = {"veredito": "um_video", "titulo": "Dia de IKEA", "mensagem": "a estante nova", "gancho": hook,
               "capitulos": [{"titulo": "Ida", "takes": ["T02", "T03"]}, {"titulo": "Volta", "takes": ["T01", "T04"]}]}
    model = Scripted(outline)
    report = planner.plan_stories(inventory, model, tmp_path)
    video = report.proposals[0].videos[0]
    assert video.title == "Dia de IKEA" and len(model.calls) == 3
    assert video.beats[0].role == "gancho" and video.beats[0].take_id == "T01"
    assert video.beats[-1].role == "conclusao" and video.beats[-1].take_id == "T04"
    assert {beat.take_id for beat in video.beats} == {"T01", "T02", "T03", "T04"}
    again = Scripted(outline)
    planner.plan_stories(inventory, again, tmp_path)
    assert again.calls == []


def test_split_suggestion_becomes_a_second_proposal(tmp_path: Path):
    outline = {"titulo": "Dia", "capitulos": [{"titulo": "Loja", "takes": ["T02", "T03"]}, {"titulo": "Casa", "takes": ["T01", "T04"]}],
               "dividir": [[0], [1]]}
    report = planner.plan_stories(day_inventory(), Scripted(outline), tmp_path)
    assert [len(proposal.videos) for proposal in report.proposals] == [1, 2]
    assert report.proposals[1].videos[0].title == "Loja"


def test_duration_target_shortens_or_warns(tmp_path: Path):
    outline = {"titulo": "Dia", "capitulos": [{"titulo": "Tudo", "takes": ["T01", "T02", "T03", "T04"]}]}
    short = planner.plan_stories(day_inventory(), Scripted(outline), tmp_path / "a", target_minutes=10)
    assert any("menos da metade" in warning for warning in short.proposals[0].warnings)
    long = planner.plan_stories(day_inventory(), Scripted(outline), tmp_path / "b", target_minutes=0.25)
    assert long.proposals[0].videos[0].duration_s <= 0.25 * 60 + 10


def test_model_failure_falls_back_to_the_chronological_base(tmp_path: Path):
    class Broken(Scripted):
        def generate(self, prompt, images=None, max_tokens=700):
            return "não sei"

    report = planner.plan_stories(day_inventory(), Broken({}), tmp_path)
    video = report.proposals[0].videos[0]
    assert len(video.beats) == len(base_cut(day_inventory()).speech)


def test_music_transcribed_as_repeated_words_is_not_speech():
    from story.chronology import repetitive
    assert repetitive("Música Música Música") and repetitive("la la la la ô")
    assert not repetitive("Bom dia, hoje a gente vai no IKEA")


def test_beats_remember_their_chapter(tmp_path: Path):
    inventory = day_inventory()
    hook = next(moment.id for moment in base_cut(inventory).speech if moment.take_id == "T01")
    outline = {"titulo": "Dia", "gancho": hook,
               "capitulos": [{"titulo": "Ida", "takes": ["T02", "T03"]}, {"titulo": "Volta", "takes": ["T01", "T04"]}]}
    video = planner.plan_stories(inventory, Scripted(outline), tmp_path).proposals[0].videos[0]
    assert video.beats[0].chapter == "Abertura"
    assert {beat.chapter for beat in video.beats[1:]} == {"Ida", "Volta"}
