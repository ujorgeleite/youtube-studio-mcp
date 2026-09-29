import json
from pathlib import Path

from core.project import ReviewState
from core.schema import Sentence, Take, Transcript
from proof.benchmark import benchmark, benchmark_report
from proof.compare import compare, comparison_report
from story.validate import build_report
from tests.story_fixtures import example_inventory
from tests.test_story import FULL, _single
from tests.test_vision import FakeModel


def _edit(*texts: str) -> Transcript:
    return Transcript("EDIT", sentences=[Sentence(i * 5, i * 5 + 4, text) for i, text in enumerate(texts)])


def test_compare_measures_recall_precision_and_order():
    inventory = example_inventory()
    video = build_report(_single(FULL), inventory).proposals[0].videos[0]
    edit = _edit("Hoje a gente vai aproveitar o parque aqui perto de casa.",
                 "É nessas coisas pequenas que a gente percebe a mudança",
                 "Mas também é conseguir aproveitar um dia simples.",
                 "Música tema do canal")
    result = compare(edit, 20, video, None, inventory)
    assert result.unmatched == ["Música tema do canal"]
    assert (result.recall, result.precision, result.order_agreement) == (1.0, 0.75, 2 / 3)
    report = comparison_report(result, inventory, "final.mp4", video)
    assert "| Falas da sua edição encontradas na proposta (recall) | 100% |" in report
    assert "voltou mais leve" in report.split("A proposta usou e você não")[1]


def test_compare_respects_review_exclusions():
    inventory = example_inventory()
    video = build_report(_single(FULL), inventory).proposals[0].videos[0]
    gancho = video.beats[0].id
    result = compare(_edit("É nessas coisas pequenas que a gente percebe a mudança."), 5, video, ReviewState(excluded=[gancho]), inventory)
    assert result.recall == 0


def test_benchmark_runs_each_model_and_counts_invalid_json(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("analysis.vision.sampling", lambda: {"broad_every_s": 3, "broad_max_frames": 2, "frames_per_call": 2,
                                                              "detail_windows_per_take": 0, "detail_frames_per_window": 2})
    take = Take("T02", str(media_dir / "b_conversa.mp4"), "b_conversa.mp4", 6)
    good = json.dumps({"descricao": "sala", "interesse": .5})

    def factory(repo):
        return FakeModel(["{}", "lixo", good] if "4B" in repo else ["{}", good])

    runs = benchmark([take], {}, tmp_path, ["qwen3-vl-4b", "qwen3-vl-8b"], model_factory=factory)
    assert [(run.key, run.calls, run.invalid, run.error) for run in runs] == [("qwen3-vl-4b", 2, 1, None), ("qwen3-vl-8b", 1, 0, None)]
    report = benchmark_report(runs, [take])
    assert "| qwen3-vl-4b |" in report and "sala" in report
