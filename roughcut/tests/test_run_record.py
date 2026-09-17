"""Testa a camada de registro de execução — sem rede, sem LLM, sem Whisper."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.run_record import RunRecord, _slug  # noqa: E402


def _fixed_env() -> dict:
    return {"python": "3.14.0", "platform": "test", "ffmpeg": None, "git_sha": "abc123"}


def _make(tmp_path, **params) -> RunRecord:
    params.setdefault("format", "qualidade-de-vida")
    return RunRecord.create(tmp_path, params, environment=_fixed_env)


def _read_events(record: RunRecord) -> list[dict]:
    lines = (record.dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_create_makes_bundle_and_start_event(tmp_path):
    record = _make(tmp_path, format="meu-formato")

    assert record.dir.parent == tmp_path
    assert record.dir.name.endswith("__meu-formato")
    events = _read_events(record)
    assert events[0]["event"] == "start"
    assert events[0]["payload"]["environment"]["git_sha"] == "abc123"


def test_create_avoids_collision(tmp_path):
    first = _make(tmp_path, format="x")
    second = _make(tmp_path, format="x")

    assert first.dir != second.dir


def test_event_appends_structured_lines(tmp_path):
    record = _make(tmp_path)

    record.event("order", "llm_call", tokens_in=1200, tokens_out=800)

    last = _read_events(record)[-1]
    assert last["step"] == "order"
    assert last["event"] == "llm_call"
    assert last["level"] == "info"
    assert last["payload"] == {"tokens_in": 1200, "tokens_out": 800}
    assert "ts" in last and "elapsed_ms" in last


def test_step_records_ok_timing(tmp_path):
    record = _make(tmp_path)

    with record.step("assemble", output="out.mp4"):
        pass

    record.finalize("ok")
    manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["steps"] == [
        {"step": "assemble", "status": "ok", "duration_ms": manifest["steps"][0]["duration_ms"]}
    ]
    kinds = [e["event"] for e in _read_events(record)]
    assert "step_start" in kinds and "step_end" in kinds


def test_step_records_error_and_reraises(tmp_path):
    record = _make(tmp_path)

    with pytest.raises(ValueError):
        with record.step("order"):
            raise ValueError("boom")

    error_event = next(e for e in _read_events(record) if e["event"] == "step_error")
    assert error_event["level"] == "error"
    assert error_event["payload"]["error"] == "boom"
    assert error_event["payload"]["error_type"] == "ValueError"


def test_artifact_writes_json_and_text(tmp_path):
    record = _make(tmp_path)

    json_path = record.artifact("cut_list", {"roughcut": []}, filename="cut-list.json")
    text_path = record.artifact("prompt", "olá prompt", filename="prompt.md")

    assert json.loads(json_path.read_text(encoding="utf-8")) == {"roughcut": []}
    assert text_path.read_text(encoding="utf-8") == "olá prompt"


def test_finalize_writes_manifest_with_artifacts_and_env(tmp_path):
    record = _make(tmp_path, format="f", model_size="base")
    record.artifact("transcripts", "bloco", filename="transcripts.txt")
    record.note_output("stringout", "/abs/out.mp4")

    record.finalize("ok")

    manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ok"
    assert manifest["error"] is None
    assert manifest["params"]["model_size"] == "base"
    assert manifest["environment"] == _fixed_env()
    assert manifest["artifacts"]["transcripts"] == "transcripts.txt"
    assert manifest["artifacts"]["stringout"] == "/abs/out.mp4"
    assert "created_at" in manifest and "finished_at" in manifest


def test_finalize_error_carries_message(tmp_path):
    record = _make(tmp_path)

    record.finalize("error", error="algo quebrou")

    manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "error"
    assert manifest["error"] == "algo quebrou"


def test_slug_normalizes():
    assert _slug("Qualidade de Vida!") == "qualidade-de-vida"
    assert _slug("  ") == "run"
