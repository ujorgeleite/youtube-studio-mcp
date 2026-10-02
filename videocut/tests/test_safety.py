"""O VideoCut nunca apaga, move ou sobrescreve nada na pasta de origem."""
import hashlib
import os
import shutil
from pathlib import Path

import pytest

from core.project import Project
from core.safety import SourceProtectionError, ensure_writable, is_protected, protect, write_text
from core.serial import write_json
from media.probe import run_ffmpeg


def snapshot(folder: Path) -> dict[str, tuple[int, str]]:
    return {path.relative_to(folder).as_posix(): (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(folder.rglob("*")) if path.is_file()}


@pytest.fixture
def raw(media_dir: Path, tmp_path: Path) -> Path:
    folder = tmp_path / "raw"
    folder.mkdir()
    for name in ("a_passeio.mov", "b_conversa.mp4"):
        shutil.copy(media_dir / name, folder / name)
    shutil.copy(media_dir / "b_conversa.mp4", folder / "b_conversa.LRF")
    return folder


def test_protection_covers_the_folder_its_children_and_symlinks(raw: Path, tmp_path: Path):
    protect(raw)
    link = tmp_path / "atalho"
    os.symlink(raw, link)
    assert is_protected(raw) and is_protected(raw / "b_conversa.mp4") and is_protected(link / "novo.mp4")
    assert not is_protected(tmp_path / "raw__videocut")
    with pytest.raises(SourceProtectionError):
        ensure_writable(link / "b_conversa.mp4")


def test_output_inside_the_source_folder_is_refused(raw: Path):
    for output in (raw, raw / "saida"):
        with pytest.raises(SourceProtectionError):
            Project.open(raw, output)
    assert Project.open(raw).output_dir.endswith("raw__videocut")


def test_no_writer_can_touch_source_files(raw: Path):
    protect(raw)
    before = snapshot(raw)
    original = raw / "b_conversa.mp4"
    with pytest.raises(SourceProtectionError):
        run_ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=16x16:d=1"], output=original, error="x")
    with pytest.raises(SourceProtectionError):
        write_json(raw / "project.json", {"a": 1})
    with pytest.raises(SourceProtectionError):
        write_text(raw / "notas.md", "x")
    assert snapshot(raw) == before


def test_full_analysis_and_delivery_leave_the_source_folder_identical(raw: Path, monkeypatch):
    from analysis import pipeline
    from analysis.speech import group_sentences
    from core.schema import Transcript, Word
    from media.catalog import catalog_folder
    from montage import render
    from montage.delivery import deliver
    from tests.test_pipeline import ScriptedModel

    before = snapshot(raw)
    monkeypatch.setattr("analysis.vision.sampling", lambda: {"broad_every_s": 3, "broad_max_frames": 2, "frames_per_call": 2,
                                                              "detail_windows_per_take": 1, "detail_frames_per_window": 2})
    words = [Word(0.5, 1.0, "Hoje"), Word(1.1, 1.6, "passeamos"), Word(1.7, 2.1, "no"), Word(2.2, 2.8, "parque.")]
    monkeypatch.setattr(pipeline, "transcribe_take", lambda take_id, *a, **k: Transcript(take_id, words=words, sentences=group_sentences(words)))
    monkeypatch.setattr(pipeline, "release_model", lambda: None)
    monkeypatch.setattr(render, "video_encoder", lambda: ["-c:v", "libx264", "-preset", "ultrafast"])

    project = Project.open(raw)
    project.takes, _ = catalog_folder(raw, project.layout.thumbnails)
    project.selected = [take.id for take in project.takes]
    report = pipeline.Analysis(project, model_factory=ScriptedModel).run()
    proposal = report.proposals[0]
    artifacts = deliver(proposal, proposal.videos[0], pipeline.load_inventory(project), None,
                        project.layout.delivery(proposal.id, proposal.videos[0].id), project.layout.work / "render")

    assert Path(artifacts["video"]).is_file()
    assert snapshot(raw) == before
