from __future__ import annotations

from pathlib import Path

import pytest

from silence.analyze import extract_thumbnail, parse_silencedetect, resolve_analysis_source
from tests.fixtures.make_clips import make_clips


def test_parse_silencedetect_handles_leading_internal_and_trailing():
    log = """
    [silencedetect] silence_start: 0
    [silencedetect] silence_end: 3.2 | silence_duration: 3.2
    [silencedetect] silence_start: 8.5
    [silencedetect] silence_end: 10.0 | silence_duration: 1.5
    [silencedetect] silence_start: 18.0
    """
    result = parse_silencedetect(log, 20.0)
    assert [(item.start_s, item.end_s) for item in result] == [
        (0.0, 3.2),
        (8.5, 10.0),
        (18.0, 20.0),
    ]


def test_parse_silencedetect_accepts_silence_already_in_progress():
    result = parse_silencedetect("silence_end: 1.25 | silence_duration: 1.25", 8.0)
    assert [(item.start_s, item.end_s) for item in result] == [(0.0, 1.25)]


def test_extract_thumbnail_creates_jpeg_without_touching_video(tmp_path):
    source = make_clips(str(tmp_path / "raw"))["C01"]
    source_mtime = (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns

    thumbnail = extract_thumbnail(source, tmp_path / "thumbs" / "C01.jpg", duration_s=5)

    assert thumbnail.is_file()
    assert thumbnail.stat().st_size > 0
    assert (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns == source_mtime


def test_resolve_analysis_source_uses_valid_lrf_proxy(tmp_path, monkeypatch):
    original = tmp_path / "DJI_0001.MP4"
    proxy = tmp_path / "DJI_0001.LRF"
    original.touch(); proxy.touch()
    monkeypatch.setattr(
        "silence.analyze.probe_media",
        lambda path: (60.0, True) if Path(path).suffix == ".MP4" else (60.1, True),
    )

    chosen, kind, delta = resolve_analysis_source(original)

    assert chosen == proxy
    assert kind == "dji_lrf_proxy"
    assert delta == pytest.approx(0.1)


def test_resolve_analysis_source_falls_back_when_proxy_duration_is_wrong(tmp_path, monkeypatch):
    original = tmp_path / "DJI_0001.MP4"
    proxy = tmp_path / "DJI_0001.LRF"
    original.touch(); proxy.touch()
    monkeypatch.setattr(
        "silence.analyze.probe_media",
        lambda path: (60.0, True) if Path(path).suffix == ".MP4" else (70.0, True),
    )

    chosen, kind, delta = resolve_analysis_source(original)

    assert chosen == original
    assert kind == "original"
    assert delta == 0.0
