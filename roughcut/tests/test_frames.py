"""Testa a extração de frames — ffmpeg/ffprobe mockados, sem mídia real."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps import frames  # noqa: E402


def test_timestamps_respects_interval_and_limit():
    assert frames._timestamps(0, 5, 8) == [0.0]
    assert frames._timestamps(12, 5, 8) == [0.0, 5.0, 10.0]
    assert len(frames._timestamps(1000, 5, 8)) == 8


def test_grid_frames_writes_one_per_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(frames, "_probe_duration", lambda src: 8.0)
    written = []

    def fake_extract(src, at, dest, width=frames.THUMB_WIDTH):
        open(dest, "w").close()
        written.append((src, at, os.path.basename(dest)))

    monkeypatch.setattr(frames, "extract_frame", fake_extract)

    result = frames.grid_frames({"C01": "/a.mp4"}, str(tmp_path), every_seconds=5.0)

    assert [r["path"] for r in result] == ["grid_C01_00.jpg", "grid_C01_01.jpg"]
    assert all(r["kind"] == "grid" for r in result)
    assert len(written) == 2


def test_cold_open_frames_extracts_midpoint(tmp_path, monkeypatch):
    captured = {}

    def fake_extract(src, at, dest, width=frames.THUMB_WIDTH):
        open(dest, "w").close()
        captured["at"] = at
        captured["src"] = src

    monkeypatch.setattr(frames, "extract_frame", fake_extract)
    cut_list = {
        "roughcut": [
            {"beat": "cold_open", "clips": [{"clip_id": "C01", "in": "00:00:02", "out": "00:00:06"}]},
            {"beat": "entrada", "clips": [{"clip_id": "C02", "in": "0", "out": "1"}]},
        ]
    }

    result = frames.cold_open_frames(cut_list, {"C01": "/a.mp4"}, str(tmp_path))

    assert len(result) == 1
    assert result[0]["clip_id"] == "C01"
    assert result[0]["kind"] == "cold_open"
    assert captured["at"] == 4.0
    assert captured["src"] == "/a.mp4"


def test_cold_open_frames_skips_missing_clip(tmp_path, monkeypatch):
    monkeypatch.setattr(frames, "extract_frame", lambda *a, **k: None)
    cut_list = {"roughcut": [{"beat": "cold_open", "clips": [{"clip_id": "CX", "in": "0", "out": "1"}]}]}

    assert frames.cold_open_frames(cut_list, {"C01": "/a.mp4"}, str(tmp_path)) == []
