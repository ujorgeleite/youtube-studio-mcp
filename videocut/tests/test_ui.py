"""Monta as páginas reais do NiceGUI em memória e exercita os callbacks."""
import asyncio
from pathlib import Path

from nicegui import Client, core, ui
from nicegui.page import page

from core.project import Project
from media.catalog import catalog_folder
from tests.test_pipeline import ScriptedModel
from ui import analysis_view, material, state
from ui.shell import Shell
from ui.state import ANALYSIS, MATERIAL, STORIES, Studio


def _renderers():
    return {MATERIAL: material.render, ANALYSIS: analysis_view.render,
            STORIES: lambda shell: ui.label("histórias"), 3: lambda shell: None, 4: lambda shell: None}


def _texts(client) -> list[str]:
    return [getattr(element, "text", "") for element in client.elements.values()]


def _project(media_dir: Path, tmp_path: Path) -> Project:
    project = Project.open(media_dir, tmp_path / "out")
    project.takes, _ = catalog_folder(media_dir, project.layout.thumbnails)
    project.selected = [take.id for take in project.takes]
    return project


def test_material_shows_takes_badges_and_selection(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(state, "LAST_PROJECT", tmp_path / "last.json")
    studio = Studio()
    studio.use(_project(media_dir, tmp_path))
    with Client(page("/material-test")) as client:
        Shell(studio, _renderers()).build()
        texts = _texts(client)
        assert "T01 · a_passeio.mov" in texts and "T02 · b_conversa.mp4" in texts
        assert "sem áudio" in texts
        assert any(text.startswith("2 selecionados") for text in texts)
        assert any(text.startswith("Projeto / raw") for text in texts)


def test_analysis_runs_in_background_and_moves_to_stories(media_dir: Path, tmp_path: Path, monkeypatch):
    from tests import test_pipeline

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(state, "LAST_PROJECT", tmp_path / "last.json")
    monkeypatch.setattr(analysis_view.run, "io_bound", inline)
    monkeypatch.setattr(analysis_view, "MODEL_FACTORY", ScriptedModel)
    monkeypatch.setattr("analysis.pipeline.transcribe_take", lambda take_id, *a, **k: test_pipeline.Transcript(
        take_id, words=[test_pipeline.Word(0.5, 1.0, "Olá.")], sentences=[test_pipeline.group_sentences([test_pipeline.Word(0.5, 1.0, "Olá.")])[0]]))
    monkeypatch.setattr("analysis.pipeline.release_model", lambda: None)
    monkeypatch.setattr("analysis.vision.sampling", lambda: {"broad_every_s": 3, "broad_max_frames": 2, "frames_per_call": 2,
                                                              "detail_windows_per_take": 0, "detail_frames_per_window": 2})
    studio = Studio()
    studio.use(_project(media_dir, tmp_path))

    async def exercise():
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        with Client(page("/analysis-test")) as client:
            shell = Shell(studio, _renderers())
            shell.build()
            await analysis_view.start_analysis(shell)
            await asyncio.sleep(0.05)
            assert studio.page == STORIES and not studio.analyzing
            assert studio.project.report.proposals
            assert "histórias" in _texts(client)
            shell.go(ANALYSIS)
            await asyncio.sleep(0.05)
            assert "2 / 2" in _texts(client)

    asyncio.run(exercise())
