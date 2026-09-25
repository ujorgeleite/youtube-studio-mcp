"""Resumo persistente e incremental de um lote do Corte inteligente."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


TERMINAL_STAGES = {"Concluído", "Falhou", "Sem áudio — ignorado"}


def _cuts_removed(entry: dict[str, Any]) -> float:
    plan = entry.get("plan")
    if not plan:
        return 0.0
    disabled = entry.get("disabled_cuts", set())
    return round(sum(cut.end_s - cut.start_s for index, cut in enumerate(plan.cuts) if index not in disabled), 3)


def entry_report_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Converte o estado transitório da interface em uma linha serializável."""
    original_s = round(float(entry.get("duration", 0)), 3)
    removed_s = _cuts_removed(entry)
    artifacts = {
        name: str(path)
        for name, path in entry.get("artifacts", {}).items()
    }
    if entry.get("rendered"):
        artifacts["mp4"] = str(entry["rendered"])
    return {
        "source": entry.get("path", ""),
        "name": entry.get("name", ""),
        "status": entry.get("stage", "Pronto para analisar"),
        "error": entry.get("error"),
        "original_s": original_s,
        "final_s": round(max(0.0, original_s - removed_s), 3),
        "removed_s": removed_s,
        "removed_pct": round(100 * removed_s / original_s, 2) if original_s else 0.0,
        "cuts": sum(1 for index, _ in enumerate(entry.get("plan").cuts) if index not in entry.get("disabled_cuts", set())) if entry.get("plan") else 0,
        "analysis_s": round(float(entry.get("analysis_elapsed_s", 0)), 3),
        "render_s": round(float(entry.get("render_elapsed_s", 0)), 3),
        "completed_at": entry.get("completed_at"),
        "artifacts": artifacts,
    }


def build_batch_summary(batch: dict[str, Any], entries: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Cria um resumo estável mesmo enquanto parte do lote ainda está rodando."""
    now = now or datetime.now()
    target_paths = set(batch.get("targets", []))
    rows = [entry_report_row(entry) for entry in entries if entry.get("path") in target_paths]
    original_s = sum(row["original_s"] for row in rows)
    removed_s = sum(row["removed_s"] for row in rows)
    started_at = batch.get("started_at")
    started = datetime.fromisoformat(started_at) if started_at else now
    elapsed_s = max(0.0, (now - started).total_seconds())
    status_counts = {status: sum(row["status"] == status for row in rows) for status in TERMINAL_STAGES}
    finished = len(rows) and all(row["status"] in TERMINAL_STAGES for row in rows)
    return {
        "schema_version": 1,
        "batch_id": batch.get("id"),
        "mode": batch.get("mode"),
        "started_at": started.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed_s, 3),
        "finished": finished,
        "videos": {
            "total": len(rows),
            "completed": status_counts["Concluído"],
            "failed": status_counts["Falhou"],
            "without_audio": status_counts["Sem áudio — ignorado"],
            "in_progress": sum(row["status"] not in TERMINAL_STAGES for row in rows),
        },
        "duration": {
            "original_s": round(original_s, 3),
            "final_s": round(max(0.0, original_s - removed_s), 3),
            "removed_s": round(removed_s, 3),
            "removed_pct": round(100 * removed_s / original_s, 2) if original_s else 0.0,
            "removed_per_processing_second": round(removed_s / elapsed_s, 3) if elapsed_s else None,
        },
        "rows": rows,
    }


def write_batch_summary(output_dir: str | Path, summary: dict[str, Any]) -> dict[str, Path]:
    """Atualiza JSON e Markdown que podem ser consultados antes do fim do lote."""
    reports = Path(output_dir).resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stem = f"{summary.get('batch_id', 'lote')}__summary"
    json_path = reports / f"{stem}.json"
    markdown_path = reports / f"{stem}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    duration = summary["duration"]
    videos = summary["videos"]
    lines = [
        "# Resumo do lote",
        "",
        f"- Modo: {summary.get('mode', 'desconhecido')}",
        f"- Iniciado: {summary['started_at']}",
        f"- Atualizado: {summary['updated_at']}",
        f"- Tempo de processamento: {summary['elapsed_s']:.1f}s",
        f"- Vídeos: {videos['completed']} concluídos, {videos['failed']} falharam, {videos['without_audio']} sem áudio, {videos['in_progress']} em andamento",
        f"- Duração: {duration['original_s']:.1f}s → {duration['final_s']:.1f}s; {duration['removed_s']:.1f}s removidos ({duration['removed_pct']:.1f}%)",
        "",
        "## Vídeos",
        "",
    ]
    for row in summary["rows"]:
        detail = f"{row['original_s']:.1f}s → {row['final_s']:.1f}s · {row['removed_s']:.1f}s removidos"
        lines.append(f"- **{row['name']}** — {row['status']} · {detail}")
        if row["error"]:
            lines.append(f"  - Erro: {row['error']}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
