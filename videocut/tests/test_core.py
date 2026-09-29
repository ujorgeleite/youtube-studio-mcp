from pathlib import Path

from core.cache import StageCache, fingerprint
from core.project import STAGE_READY, Project, ReviewState, TakeStatus, default_output_dir
from core.schema import (
    Beat, Criterion, EditPlan, Evidence, Overlay, Proposal, StoryReport, StoryVideo, Take, Transcript,
    VideoClip, Word,
)
from core.serial import from_data, to_data
from core.timefmt import clock, parse_clock, span, stopwatch


def _report() -> StoryReport:
    beat = Beat("b1", "Gancho", "gancho", "T03", 18, 36, "abre com a ideia",
                overlays=[Overlay("T06", 5, 9, at_s=2)],
                evidence=[Evidence("T03", 18, 36, quote="coisas pequenas")])
    video = StoryVideo("v1", "A adaptação", "mensagem", [beat])
    proposal = Proposal("A", "Um vídeo", videos=[video],
                        criteria=[Criterion("mensagem", "ok"), Criterion("encerramento", "revisar")])
    return StoryReport("um_video", "resumo", ["rotina"], proposals=[proposal])


def test_nested_dataclasses_roundtrip_through_plain_data():
    report = _report()
    restored = from_data(StoryReport, to_data(report))
    assert restored == report
    assert restored.proposals[0].videos[0].beats[0].overlays[0].duration_s == 4
    assert restored.proposals[0].review_points == 1


def test_unknown_keys_are_ignored_for_forward_compatibility():
    take = from_data(Take, {"id": "T01", "path": "/a.mp4", "name": "a", "duration_s": 3, "novo": 1})
    assert take.id == "T01"


def test_transcript_text_between_uses_word_boundaries():
    transcript = Transcript("T01", words=[Word(0, .5, "Olá"), Word(.6, 1, "mundo"), Word(2, 3, "fim")])
    assert transcript.text_between(0, 1) == "Olá mundo"


def test_edit_plan_duration_ignores_broll_track():
    plan = EditPlan("A", "v1", "t", video=[VideoClip("T01", 0, 10, 0, "b1"), VideoClip("T02", 0, 4, 12, "b1", broll=True)])
    assert plan.duration_s == 10
    assert len(plan.broll_track) == 1


def test_project_persists_choices_and_reopens(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    project = Project.open(raw)
    assert Path(project.output_dir) == default_output_dir(raw)
    project.takes = [Take("T01", str(raw / "a.mp4"), "a.mp4", 10)]
    project.selected = ["T01"]
    project.status["T01"] = TakeStatus(STAGE_READY, 1.0)
    project.report = _report()
    project.review["v1"] = ReviewState(order=["b1"], excluded=[])
    project.save()

    again = Project.open(raw)
    assert again.selected_takes[0].name == "a.mp4"
    assert again.status["T01"].stage == STAGE_READY
    assert again.report.proposals[0].id == "A"
    assert again.review["v1"].order == ["b1"]
    assert again.layout.delivery("A", "v1").name == "proposta-a__v1"


def test_stage_cache_separates_model_variants(tmp_path: Path):
    source = tmp_path / "a.mp4"
    source.write_bytes(b"x")
    cache = StageCache(tmp_path / ".cache", source)
    cache.save("vision", {"model": "4b"}, variant=fingerprint("4b"))
    assert cache.load("vision", variant=fingerprint("8b")) is None
    assert cache.load("vision", variant=fingerprint("4b")) == {"model": "4b"}


def test_time_formatting():
    assert clock(75.4) == "01:15"
    assert clock(3725) == "1:02:05"
    assert stopwatch(8) == "00:00:08"
    assert span(40, 120) == "00:40–02:00"
    assert parse_clock("01:12.5") == 72.5
    assert parse_clock(3) == 3.0


def test_merge_takes_deselects_only_new_short_takes(tmp_path: Path):
    project = Project.open(tmp_path / "raw")
    project.takes = [Take("T01", "/a", "a", 2), Take("T02", "/b", "b", 60)]
    project.selected = ["T01"]
    skipped = project.merge_takes([Take("T01", "/a", "a", 2), Take("T02", "/b", "b", 60),
                                   Take("T03", "/c", "c", 3), Take("T04", "/d", "d", 30)], min_take_s=5)
    assert [take.id for take in skipped] == ["T03"]
    assert project.selected == ["T01", "T04"]
    assert [take.id for take in project.short_takes(5)] == ["T01", "T03"]
