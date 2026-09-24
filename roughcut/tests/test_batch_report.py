import json
from datetime import datetime, timedelta

from smartcut.batch_report import build_batch_summary, write_batch_summary
from smartcut.schema import Cut, CutPlan


def test_batch_summary_updates_a_completed_video_and_persists_files(tmp_path):
    started = datetime(2026, 9, 24, 12, 0, 0)
    entry = {
        "path": "/raw/a.mp4", "name": "a.mp4", "duration": 20,
        "stage": "Concluído", "plan": CutPlan("a.mp4", 20, "colab", cuts=[Cut(4, 7, "pausa_na_frase")]),
        "disabled_cuts": set(), "analysis_elapsed_s": 2.5, "render_elapsed_s": 8.25,
        "rendered": "/out/videos/processed_a.mp4", "artifacts": {"srt": tmp_path / "a.srt"},
    }
    batch = {"id": "20260924-120000", "mode": "renderização", "started_at": started.isoformat(), "targets": [entry["path"]]}

    summary = build_batch_summary(batch, [entry], now=started + timedelta(seconds=10))

    assert summary["finished"] is True
    assert summary["videos"] == {"total": 1, "completed": 1, "failed": 0, "without_audio": 0, "in_progress": 0}
    assert summary["duration"]["removed_s"] == 3
    assert summary["duration"]["removed_per_processing_second"] == 0.3
    assert summary["rows"][0]["artifacts"]["mp4"].endswith("processed_a.mp4")

    paths = write_batch_summary(tmp_path, summary)
    saved = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert saved["rows"][0]["status"] == "Concluído"
    assert "a.mp4" in paths["markdown"].read_text(encoding="utf-8")


def test_batch_summary_keeps_non_terminal_videos_in_progress():
    batch = {"id": "lote", "mode": "análise", "started_at": "2026-09-24T12:00:00", "targets": ["/raw/a.mp4"]}
    summary = build_batch_summary(batch, [{"path": "/raw/a.mp4", "name": "a.mp4", "duration": 12, "stage": "Detectando fala e transcrevendo"}], now=datetime(2026, 9, 24, 12, 0, 3))

    assert summary["finished"] is False
    assert summary["videos"]["in_progress"] == 1
