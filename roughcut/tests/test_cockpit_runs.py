"""Testa os helpers puros do cockpit — sem UI, sem rede."""

from __future__ import annotations

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cockpit.runs import list_runs, load_manifest, read_events, zip_run  # noqa: E402


def _make_bundle(root, run_id, status="ok"):
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": run_id, "status": status, "steps": []}), encoding="utf-8"
    )
    (run_dir / "events.jsonl").write_text(
        '{"step": "run", "event": "start", "level": "info", "payload": {}}\n', encoding="utf-8"
    )
    (run_dir / "cut-list.json").write_text('{"roughcut": []}', encoding="utf-8")
    return run_dir


def test_list_runs_empty(tmp_path):
    assert list_runs(tmp_path) == []


def test_list_runs_sorted_desc_with_manifest(tmp_path):
    _make_bundle(tmp_path, "2026-09-17T10-00-00__a")
    _make_bundle(tmp_path, "2026-09-17T12-00-00__b", status="error")

    runs = list_runs(tmp_path)

    assert [r["run_id"] for r in runs] == [
        "2026-09-17T12-00-00__b",
        "2026-09-17T10-00-00__a",
    ]
    assert runs[0]["status"] == "error"


def test_load_manifest_missing_returns_none(tmp_path):
    assert load_manifest(tmp_path / "nope") is None


def test_read_events_parses_lines(tmp_path):
    run_dir = _make_bundle(tmp_path, "r1")

    events = read_events(run_dir)

    assert events == [{"step": "run", "event": "start", "level": "info", "payload": {}}]


def test_zip_run_bundles_all_files(tmp_path):
    run_dir = _make_bundle(tmp_path, "r1")

    zip_path = zip_run(run_dir)

    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert {"run.json", "events.jsonl", "cut-list.json"} <= names
