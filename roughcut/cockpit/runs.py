"""Consultas sobre a pasta runs/ — puro, sem UI. Espelha o que a camada de
run-record escreve e empacota um bundle para análise por IA."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE.parent / "runs"


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def load_manifest(run_dir: str | Path) -> dict[str, Any] | None:
    manifest = Path(run_dir) / "run.json"
    if not manifest.is_file():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_runs(runs_dir: str | Path = RUNS_DIR) -> list[dict[str, Any]]:
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    runs = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        manifest = load_manifest(entry)
        runs.append(
            {
                "run_id": entry.name,
                "dir": str(entry),
                "manifest": manifest,
                "status": (manifest or {}).get("status", "unknown"),
                "size_bytes": _dir_size(entry),
            }
        )
    runs.sort(key=lambda r: r["run_id"], reverse=True)
    return runs


def delete_run(run_dir: str | Path, runs_dir: str | Path = RUNS_DIR) -> None:
    """Apaga o bundle gerado de um run. Recusa qualquer caminho fora de runs/ —
    nunca toca na pasta de clipes de origem."""
    target = Path(run_dir).resolve()
    root = Path(runs_dir).resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"recusado: {target} não está dentro de {root}")
    shutil.rmtree(target)
    zip_beside = target.parent / f"{target.name}.zip"
    if zip_beside.is_file():
        zip_beside.unlink()


def read_events(run_dir: str | Path) -> list[dict[str, Any]]:
    events_file = Path(run_dir) / "events.jsonl"
    if not events_file.is_file():
        return []
    lines = events_file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def zip_run(run_dir: str | Path, dest_dir: str | Path | None = None) -> Path:
    """Empacota o bundle inteiro num .zip pronto para entregar a uma IA."""
    source = Path(run_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"run não encontrado: {source}")
    target_dir = Path(dest_dir) if dest_dir else source.parent
    zip_path = target_dir / f"{source.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source))
    return zip_path
