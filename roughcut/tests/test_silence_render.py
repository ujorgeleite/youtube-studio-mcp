from __future__ import annotations

import json
import subprocess

import pytest

from silence import render
from silence.render import default_output_dir, render_plan
from tests.fixtures.make_clips import make_clips


def _duration(path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def test_default_output_is_identified_and_sibling_of_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    output = default_output_dir(raw)
    assert output.parent == tmp_path
    assert output.name.startswith("raw__remocao-de-silencios_")


def test_render_plan_creates_new_video_and_json_without_touching_source(tmp_path):
    source = make_clips(str(tmp_path / "raw"))["C01"]
    source_mtime = (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns
    output_dir = tmp_path / "raw__remocao-de-silencios_test"
    progress = []
    plan = {
        "source": source,
        "mode": "all",
        "duration_s": 5.0,
        "keep": [{"start_s": 0.5, "end_s": 1.5}, {"start_s": 3.0, "end_s": 4.0}],
    }

    output, plan_path = render_plan(plan, output_dir, lambda done, total: progress.append((done, total)))

    assert output.parent == output_dir
    assert output.name == "C01__sem-silencios.mp4"
    assert plan_path.is_file()
    assert _duration(output) == pytest.approx(2.0, abs=0.2)
    assert progress == [(0, 2), (2, 2)]
    assert (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns == source_mtime


def test_render_plan_copies_original_when_removal_is_not_relevant(tmp_path):
    source = make_clips(str(tmp_path / "raw"))["C01"]
    plan = {
        "source": source,
        "duration_s": 5.0,
        "keep": [{"start_s": 0.0, "end_s": 4.8}],
        "render_options": {"min_removed_s": 1.0, "min_removed_pct": 0.25},
    }

    output, plan_path = render_plan(plan, tmp_path / "out")

    assert output.read_bytes() == (tmp_path / "raw" / "C01.mp4").read_bytes()
    assert json.loads(plan_path.read_text())["render"]["strategy"] == "copy_original"


def test_render_prefers_macos_hardware_encoder_when_ffmpeg_supports_it(monkeypatch):
    class Result:
        stdout = " V....D h264_videotoolbox VideoToolbox H.264 Encoder"

    render._video_encoder_args.cache_clear()
    monkeypatch.setattr(render.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(render.subprocess, "run", lambda *args, **kwargs: Result())

    assert render._video_encoder_args()[:2] == ["-c:v", "h264_videotoolbox"]
    render._video_encoder_args.cache_clear()
