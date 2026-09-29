from pathlib import Path

import pytest

from core.schema import Take
from media.audio import extract_speech_audio, make_proxy
from media.catalog import catalog_folder
from media.frames import broad_sample_times, extract_frames, merge_times, scene_changes, spread_times
from media.probe import MediaError, _rotation, list_videos, probe


def test_list_videos_filters_extensions_and_sorts(media_dir: Path):
    assert [path.name for path in list_videos(media_dir)] == ["a_passeio.mov", "b_conversa.mp4", "c_quebrado.mp4"]


def test_probe_reads_dimensions_duration_and_audio(media_dir: Path):
    info = probe(media_dir / "b_conversa.mp4")
    assert (info.width, info.height, info.fps) == (320, 240, 25.0)
    assert info.duration_s == pytest.approx(6, abs=0.1)
    assert info.has_audio
    assert not probe(media_dir / "a_passeio.mov").has_audio


def test_probe_rejects_unreadable_file(media_dir: Path):
    with pytest.raises(MediaError):
        probe(media_dir / "c_quebrado.mp4")


def test_rotation_swaps_portrait_phone_video():
    assert _rotation({"side_data_list": [{"rotation": -90}]}) == 90
    assert _rotation({"tags": {"rotate": "180"}}) == 0


def test_sampling_is_spread_and_deduplicated():
    assert spread_times(0, 10, 2) == [2.5, 7.5]
    assert len(broad_sample_times(600)) == 24
    assert len(broad_sample_times(5)) == 3
    assert merge_times([1.0, 5.0], [5.5, 9.0]) == [1.0, 5.0, 9.0]


def test_scene_change_detects_hard_cut(media_dir: Path):
    changes = scene_changes(media_dir / "b_conversa.mp4")
    assert any(abs(change - 3.0) < 0.2 for change in changes)


def test_frames_audio_and_proxy_are_cached(media_dir: Path, tmp_path: Path):
    source = media_dir / "b_conversa.mp4"
    frames = extract_frames(source, [1.0, 4.0], tmp_path / "frames", "T01")
    assert all(path.is_file() for _, path in frames)
    first_mtime = frames[0][1].stat().st_mtime_ns
    assert extract_frames(source, [1.0], tmp_path / "frames", "T01")[0][1].stat().st_mtime_ns == first_mtime
    wav = extract_speech_audio(source, tmp_path / "audio" / "T01.wav")
    assert probe_audio_rate(wav) == "16000"
    proxy = make_proxy(source, tmp_path / "proxy" / "T01.mp4", height=120)
    assert probe(proxy).height == 120


def probe_audio_rate(path: Path) -> str:
    import subprocess
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                           "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True).stdout.strip()


def test_catalog_keeps_ids_and_reports_failures(media_dir: Path, tmp_path: Path):
    takes, failed = catalog_folder(media_dir, tmp_path / "thumbs")
    assert [(take.id, take.name) for take in takes] == [("T01", "a_passeio.mov"), ("T02", "b_conversa.mp4")]
    assert "c_quebrado.mp4" in failed
    assert all(Path(take.thumbnail).is_file() for take in takes)

    known = [Take("T07", takes[1].path, "b_conversa.mp4", 6)]
    again, _ = catalog_folder(media_dir, tmp_path / "thumbs", known)
    assert [take.id for take in again] == ["T08", "T07"]
