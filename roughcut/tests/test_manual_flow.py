"""Testa o fluxo manual (copiar prompt / colar resposta) — sem Whisper nem ffmpeg."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run as pipeline  # noqa: E402
from steps.run_record import RunRecord  # noqa: E402


def _record(tmp_path, **params) -> RunRecord:
    return RunRecord.create(tmp_path, params or {"mode": "manual"}, environment=lambda: {})


def test_transcribe_and_prompt_builds_prompt_without_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "transcribe_folder",
        lambda input, model_size: ("[C01] arquivo=a.mp4\n00:00:00–00:00:05 oi", {"C01": "/a.mp4"}),
    )
    record = _record(tmp_path, mode="manual", format="qualidade-de-vida")

    prompt, clip_map = pipeline.transcribe_and_prompt(
        input="x", format="qualidade-de-vida", record=record
    )

    assert "qualidade-de-vida" in prompt
    assert "[C01] arquivo=a.mp4" in prompt
    assert clip_map == {"C01": "/a.mp4"}
    assert (record.dir / "prompt.md").is_file()
    assert (record.dir / "transcripts.txt").is_file()


def test_assemble_from_raw_parses_and_assembles(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        pipeline,
        "assemble",
        lambda cut_list, clip_map, output: captured.update(cut_list=cut_list, output=output),
    )
    record = _record(tmp_path)
    raw = '```json\n{"roughcut": [{"beat": "x", "clips": []}]}\n```'

    result = pipeline.assemble_from_raw(
        raw=raw, clip_map={"C01": "/a.mp4"}, output=str(tmp_path / "out.mp4"), record=record
    )

    assert result == {"roughcut": [{"beat": "x", "clips": []}]}
    assert captured["output"].endswith("out.mp4")
    assert (record.dir / "llm_response.txt").is_file()
    assert (record.dir / "cut-list.json").is_file()
    manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ok"


def test_assemble_from_raw_finalizes_error_on_bad_json(tmp_path):
    import pytest

    from steps.order import OrderError

    record = _record(tmp_path)

    with pytest.raises(OrderError):
        pipeline.assemble_from_raw(
            raw="desculpe, não consegui", clip_map={}, output=str(tmp_path / "out.mp4"), record=record
        )

    manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "error"
