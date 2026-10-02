import json
from pathlib import Path

import pytest

from analysis import vision
from analysis.jsontext import JsonTextError, parse_json
from analysis.vlm import ModelError, generate_json
from core.schema import Take, Transcript, VisualObservation, Word


class FakeModel:
    name = "fake-vl"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, prompt, images=None, max_tokens=700):
        self.calls.append((prompt, [Path(image) for image in images or []]))
        reply = self.replies.pop(0) if self.replies else self.default
        return reply(prompt) if callable(reply) else reply

    default = json.dumps({"descricao": "parque", "acao": "criança corre", "interesse": .8, "apoio": True})

    def release(self):
        pass


def test_parse_json_handles_fences_prose_and_trailing_commas():
    assert parse_json('Claro!\n```json\n{"a": 1,}\n```') == {"a": 1}
    assert parse_json('Resposta: {"a": "x}y", "b": [1, 2]} fim') == {"a": "x}y", "b": [1, 2]}
    with pytest.raises(JsonTextError):
        parse_json("sem json")


def test_generate_json_retries_once_then_fails():
    model = FakeModel(["nada", '{"ok": true}'])
    assert generate_json(model, "p") == {"ok": True}
    assert "somente com o JSON" in model.calls[1][0]
    with pytest.raises(ModelError):
        generate_json(FakeModel(["x", "y"]), "p")


def test_windows_cover_the_whole_take():
    windows = vision.windows_for([1, 3, 5, 7, 9], 10, 2)
    assert [(w.start_s, w.end_s) for w in windows] == [(0, 4), (4, 8), (8, 10)]
    assert vision.thin(list(range(10)), 5) == [0, 2, 4, 6, 8]


def test_observation_normalizes_loose_model_output():
    item = vision.observation_from({"descricao": " rua ", "pessoas": "uma mulher", "problemas": ["Tremido"], "interesse": "7"}, "T01", 0, 4)
    assert (item.description, item.subjects, item.issues, item.interest) == ("rua", ["uma mulher"], ["tremido"], 1.0)


def test_detail_prefers_silent_action_and_skips_unusable_frames():
    transcript = Transcript("T01", words=[Word(0, 1, "fala")])
    observations = [
        VisualObservation("T01", 0, 4, "fala", interest=.9),
        VisualObservation("T01", 4, 8, "correndo", action="corre", interest=.7),
        VisualObservation("T01", 8, 12, "preto", interest=.9, issues=["tela_preta"]),
        VisualObservation("T01", 12, 16, "parede", interest=.1),
    ]
    assert vision.detail_candidates(observations, transcript, 1) == [1]
    assert vision.detail_candidates(observations, transcript, 5) == [0, 1]


def test_refine_bounds_uses_frame_indexes():
    assert vision.refine_bounds({"inicio_frame": 2, "fim_frame": 3}, [1, 2, 3, 4], 0, 5) == (2, 3)
    assert vision.refine_bounds({"inicio_frame": 9}, [1, 2], 0, 5) == (0, 5)


def test_analyze_take_runs_two_passes_and_caches(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(vision, "sampling", lambda: {"broad_every_s": 2, "broad_max_frames": 4, "frames_per_call": 2,
                                                       "detail_windows_per_take": 1, "detail_frames_per_window": 3})
    take = Take("T02", str(media_dir / "b_conversa.mp4"), "b_conversa.mp4", 6.0)
    transcript = Transcript("T02", words=[Word(0.2, 0.8, "Olá")])
    detail = json.dumps({"descricao": "detalhe", "acao": "pula", "inicio_frame": 2, "fim_frame": 3, "interesse": .9})
    model = FakeModel([FakeModel.default, "quebrado", "quebrado", detail])
    events = []
    result = vision.analyze_take_vision(take, transcript, model, tmp_path / ".cache", tmp_path / "frames",
                                        progress=lambda fraction, message: events.append(fraction))
    assert len(model.calls) == 4
    assert "Olá" in model.calls[0][0]
    assert len(model.calls[0][1]) == 2 and len(model.calls[3][1]) == 3
    assert len(result) == 1 and result[0].detail_pass and result[0].description == "detalhe"
    assert events[-1] == 1.0

    again = vision.analyze_take_vision(take, transcript, FakeModel([]), tmp_path / ".cache", tmp_path / "frames")
    assert again == result


def test_analyze_take_fails_when_model_never_answers(media_dir: Path, tmp_path: Path):
    take = Take("T02", str(media_dir / "b_conversa.mp4"), "b_conversa.mp4", 6.0)
    silent = FakeModel([])
    silent.default = "não sei"
    with pytest.raises(ModelError):
        vision.analyze_take_vision(take, None, silent, tmp_path / ".cache", tmp_path / "frames")


def test_vision_reads_frames_from_camera_proxy(media_dir: Path, tmp_path: Path, monkeypatch):
    seen = []
    monkeypatch.setattr(vision, "scene_changes", lambda source: seen.append(source) or [])
    take = Take("T02", "/original/ausente.mp4", "ausente.mp4", 6.0, proxy=str(media_dir / "b_conversa.mp4"))
    monkeypatch.setattr(vision, "StageCache", lambda root, source: _MemoryCache())
    vision.analyze_take_vision(take, None, FakeModel([]), tmp_path / ".cache", tmp_path / "frames")
    assert seen == [take.proxy]


class _MemoryCache:
    def __init__(self):
        self.data = {}

    def load(self, stage, variant=""):
        return self.data.get((stage, variant))

    def save(self, stage, value, variant=""):
        self.data[(stage, variant)] = value
