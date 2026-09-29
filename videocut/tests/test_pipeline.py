import json
from pathlib import Path

import pytest

from analysis import pipeline
from core.project import STAGE_FAILED, STAGE_READY, Project
from core.schema import Transcript, Word
from analysis.speech import group_sentences
from media.catalog import catalog_folder


class ScriptedModel:
    """Visão quando recebe imagens; planejamento quando recebe só texto."""

    released = 0

    def __init__(self, name):
        self.name = name

    def generate(self, prompt, images=None, max_tokens=700):
        if images:
            return json.dumps({"descricao": "cena", "acao": "", "interesse": .5, "apoio": True})
        speech = next(line.split(" | ")[0] for line in prompt.splitlines() if " | fala | " in line)
        return json.dumps({"veredito": "um_video", "resumo": "ok", "propostas": [{"titulo": "Única", "recomendada": True,
                           "videos": [{"titulo": "V", "blocos": [{"momento": speech, "papel": "mensagem"}]}]}]})

    def release(self):
        ScriptedModel.released += 1


@pytest.fixture
def project(media_dir: Path, tmp_path: Path, monkeypatch) -> Project:
    monkeypatch.setattr("analysis.vision.sampling", lambda: {"broad_every_s": 3, "broad_max_frames": 2, "frames_per_call": 2,
                                                              "detail_windows_per_take": 0, "detail_frames_per_window": 2})

    def fake_transcribe(take_id, source, audio, cache_root, refresh=False):
        words = [Word(0.5, 1.0, "Hoje"), Word(1.1, 1.6, "passeamos.")]
        return Transcript(take_id, words=words, sentences=group_sentences(words))

    monkeypatch.setattr(pipeline, "transcribe_take", fake_transcribe)
    monkeypatch.setattr(pipeline, "release_model", lambda: None)
    project = Project.open(media_dir, tmp_path / "out")
    project.takes, _ = catalog_folder(media_dir, project.layout.thumbnails)
    project.selected = [take.id for take in project.takes]
    return project


def test_analysis_runs_every_stage_and_persists_report(project: Project):
    monitor = pipeline.AnalysisMonitor()
    report = pipeline.Analysis(project, monitor, model_factory=ScriptedModel).run()
    assert report.proposals[0].videos[0].beats[0].take_id == "T02"
    assert all(status.stage == STAGE_READY for status in project.status.values())
    assert monitor.stage == 3 and monitor.elapsed_s > 0
    assert any("sem trilha de áudio" in line for line in monitor.log)
    assert any("fala / Hoje passeamos." in line for line in monitor.log)
    reopened = Project.open(project.folder, project.output_dir)
    assert reopened.report.proposals[0].title == "Única"
    assert pipeline.load_inventory(reopened).moments


def test_failed_take_does_not_stop_the_batch(project: Project, monkeypatch):
    real = pipeline.analyze_take_vision

    def flaky(take, *args, **kwargs):
        if take.id == "T01":
            raise RuntimeError("frame ilegível")
        return real(take, *args, **kwargs)

    monkeypatch.setattr(pipeline, "analyze_take_vision", flaky)
    released = ScriptedModel.released
    report = pipeline.Analysis(project, model_factory=ScriptedModel).run()
    assert project.status["T01"].stage == STAGE_FAILED and "frame ilegível" in project.status["T01"].error
    assert project.status["T02"].stage == STAGE_READY and report.proposals
    assert ScriptedModel.released == released + 1


def test_cancel_stops_before_loading_the_model(project: Project):
    monitor = pipeline.AnalysisMonitor()
    monitor.cancel.set()
    with pytest.raises(pipeline.AnalysisCancelled):
        pipeline.Analysis(project, monitor, model_factory=ScriptedModel).run()
    assert monitor.finished_at > 0


def test_speech_prefers_camera_proxy_with_audio(media_dir: Path):
    from core.schema import Take
    take = Take("T01", "/original.mp4", "o.mp4", 6, proxy=str(media_dir / "b_conversa.mp4"))
    assert pipeline.speech_source(take) == take.proxy
    silent = Take("T02", "/original.mp4", "o.mp4", 6, proxy=str(media_dir / "a_passeio.mov"))
    assert pipeline.speech_source(silent) == "/original.mp4"
