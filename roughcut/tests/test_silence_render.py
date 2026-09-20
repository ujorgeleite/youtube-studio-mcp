from __future__ import annotations

import json
import subprocess

import pytest

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
        "keep": [{"start_s": 0.5, "end_s": 1.5}, {"start_s": 3.0, "end_s": 4.0}],
    }

    output, plan_path = render_plan(plan, output_dir, lambda done, total: progress.append((done, total)))

    assert output.parent == output_dir
    assert output.name == "C01__sem-silencios.mp4"
    assert plan_path.is_file()
    assert _duration(output) == pytest.approx(2.0, abs=0.2)
    assert progress == [(1, 2), (2, 2)]
    assert (tmp_path / "raw" / "C01.mp4").stat().st_mtime_ns == source_mtime

