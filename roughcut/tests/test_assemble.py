"""Testa o passo 3 (assemble) de ponta a ponta com ffmpeg real — SEM LLM, SEM Whisper.

Os clipes de amostra são cores sólidas geradas na hora; o teste verifica que o
stringout existe, tem duração ≈ soma dos trechos, e que os segmentos saíram na
ordem certa (checando a cor dominante numa amostra de cada janela de tempo).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.assemble import assemble, load_cut_list  # noqa: E402
from tests.fixtures.make_clips import make_clips  # noqa: E402

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe não instalados",
)


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def _dominant_color(path: str, at_seconds: float) -> str:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{at_seconds:.3f}", "-i", path,
            "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True,
        check=True,
    )
    r, g, b = proc.stdout[0], proc.stdout[1], proc.stdout[2]
    if max(r, g, b) < 60:
        return "black"
    return {0: "red", 1: "green", 2: "blue"}[max(range(3), key=[r, g, b].__getitem__)]


@pytest.fixture(scope="module")
def clip_map(tmp_path_factory):
    return make_clips(str(tmp_path_factory.mktemp("clips")))


@pytest.fixture(scope="module")
def cut_list():
    return load_cut_list(os.path.join(FIXTURES_DIR, "cut_list.json"))


def test_assemble_produces_output(tmp_path, cut_list, clip_map):
    out = str(tmp_path / "stringout.mp4")
    segments = assemble(cut_list, clip_map, out)

    assert os.path.exists(out)
    assert os.path.getsize(out) > 0
    # 3 clipes + 1 slug de broll
    assert [s.kind for s in segments] == ["clip", "clip", "broll", "clip"]


def test_assemble_duration_matches_sum(tmp_path, cut_list, clip_map):
    out = str(tmp_path / "stringout.mp4")
    segments = assemble(cut_list, clip_map, out)

    expected = sum(s.seconds for s in segments)  # 2 + 2 + 1 + 2 = 7
    actual = _probe_duration(out)
    assert abs(actual - expected) < 1.0, f"esperado ~{expected}s, veio {actual}s"


def test_assemble_orders_segments_correctly(tmp_path, cut_list, clip_map):
    out = str(tmp_path / "stringout.mp4")
    assemble(cut_list, clip_map, out)

    # timeline: red[0,2) green[2,4) black[4,5) blue[5,7)
    assert _dominant_color(out, 1.0) == "red"
    assert _dominant_color(out, 3.0) == "green"
    assert _dominant_color(out, 4.5) == "black"
    assert _dominant_color(out, 6.0) == "blue"


def test_cut_list_fixture_matches_schema():
    with open(os.path.join(FIXTURES_DIR, "cut_list.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert "roughcut" in data
    for beat in data["roughcut"]:
        assert "beat" in beat and "clips" in beat
        for clip in beat["clips"]:
            assert {"clip_id", "in", "out"} <= clip.keys()
