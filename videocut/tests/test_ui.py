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


def _story_studio(tmp_path: Path, monkeypatch) -> Studio:
    from core.serial import write_json
    from story.validate import build_report
    from tests.story_fixtures import example_inventory
    from tests.test_story import FULL, _single

    monkeypatch.setattr(state, "LAST_PROJECT", tmp_path / "last.json")
    inventory = example_inventory()
    project = Project.open(tmp_path / "raw", tmp_path / "out")
    project.takes = inventory.takes
    project.selected = [take.id for take in inventory.takes]
    project.report = build_report(_single(FULL), inventory)
    write_json(project.layout.analysis / "historias.json", project.report)
    write_json(project.layout.analysis / "inventario.json", inventory)
    studio = Studio()
    studio.use(project)
    return studio


def test_stories_show_proposal_and_choosing_opens_review(tmp_path: Path, monkeypatch):
    from ui import review, stories
    studio = _story_studio(tmp_path, monkeypatch)
    renderers = {**_renderers(), STORIES: stories.render, 3: review.render}

    async def exercise():
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        with Client(page("/stories-test")) as client:
            shell = Shell(studio, renderers)
            studio.page = STORIES
            shell.build()
            texts = _texts(client)
            assert "A adaptação acontece nos dias comuns" in texts and "Recomendado" in texts
            assert "O material sustenta a ideia?" in texts and "Mensagem central" in texts
            stories.choose(shell, studio.project.report.proposals[0])
            await asyncio.sleep(0.05)
            assert studio.page == 3 and "Sequência proposta" in _texts(client)
            assert studio.project.review["a1"].order == [beat.id for beat in studio.project.report.proposals[0].videos[0].beats]

    asyncio.run(exercise())


def test_review_actions_persist_and_restore(tmp_path: Path, monkeypatch):
    from ui import review, stories
    studio = _story_studio(tmp_path, monkeypatch)

    async def exercise():
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        with Client(page("/review-test")):
            shell = Shell(studio, {**_renderers(), 3: review.render})
            shell.build()
            stories.choose(shell, studio.project.report.proposals[0])
            proposal, video, state_ = review.selection(shell)
            first, second = state_.order[0], state_.order[1]
            review.move(shell, video, state_, second, -1)
            assert state_.order[:2] == [second, first]
            review.toggle(state_.protected, first)
            development = next(beat.id for beat in video.beats if beat.role == "desenvolvimento")
            review.make_shorter(shell, proposal, video, state_, 0.5)
            shorter = review.selection(shell)[1]
            assert development not in [beat.id for beat in shorter.beats]
            assert Project.open(studio.project.folder, studio.project.output_dir).review["a1"].order[:2] == [second, first]
            review.restore_original(shell, proposal, shorter)
            restored = review.selection(shell)
            assert len(restored[1].beats) == 5 and restored[2].order[0] == first

    asyncio.run(exercise())
