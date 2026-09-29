import asyncio
from pathlib import Path

import pytest
from nicegui import Client, core
from nicegui.page import page

from media.catalog import catalog_folder
from ui import activity, material, state
from ui.shell import Shell
from ui.state import Studio
from tests.test_ui import _renderers, _texts


def test_activity_lifecycle_shows_progress_then_result(monkeypatch):
    now = {"value": 10.0}
    monkeypatch.setattr(activity, "perf_counter", lambda: now["value"])
    status = activity.ActivityState()
    refreshed = []
    with activity.Activity(status, "Carregando raw", lambda: refreshed.append(1)) as step:
        assert status.running and status.visible
        step("Lendo 1/2 · a.mp4", 0.5)
        assert (status.detail, status.fraction) == ("Lendo 1/2 · a.mp4", 0.5)
        now["value"] = 12.5
    assert not status.running and status.elapsed_s == 2.5 and status.visible
    now["value"] = 20.0
    assert not status.visible
    assert len(refreshed) == 2
    assert activity.seconds(2.5) == "2,5 s" and activity.seconds(75) == "00:01:15"


def test_activity_records_errors_without_swallowing_them():
    status = activity.ActivityState()
    with pytest.raises(RuntimeError):
        with activity.Activity(status, "Prévia", lambda: None):
            raise RuntimeError("ffmpeg falhou\ndetalhe")
    assert status.error == "ffmpeg falhou" and not status.running


def test_catalog_reports_each_file(media_dir: Path, tmp_path: Path):
    events = []
    catalog_folder(media_dir, tmp_path / "thumbs", progress=lambda text, fraction: events.append((text, fraction)))
    assert events[0] == ("Lendo 1/3 · a_passeio.mov", 0.0)
    assert [text for text, _ in events][-1].startswith("Lendo 3/3")


def test_loading_a_folder_shows_the_activity_card_and_blocks_double_actions(media_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(state, "LAST_PROJECT", tmp_path / "last.json")

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(material.run, "io_bound", inline)

    async def exercise():
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        with Client(page("/activity-test")) as client:
            shell = Shell(Studio(), _renderers())
            shell.build()
            await material.open_folder(shell, str(media_dir), str(tmp_path / "out"))
            await asyncio.sleep(0.05)
            texts = _texts(client)
            assert any(text.startswith("Carregando raw") and text.endswith("concluído") for text in texts)
            assert "2 vídeo(s) prontos · 1 ignorado(s)" in texts
            shell.activity_state.start("Prévia da sequência")
            assert shell.refuse_if_working()

    asyncio.run(exercise())
