"""Renderiza um plano de remoção sem modificar o vídeo de origem."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .schema import Interval


class SilenceRenderError(RuntimeError):
    pass


def default_output_dir(input_dir: str | Path) -> Path:
    source = Path(input_dir).expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return source.parent / f"{source.name}__remocao-de-silencios_{stamp}"


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SilenceRenderError(proc.stderr.strip() or "ffmpeg falhou")


def render_plan(
    plan: dict,
    output_dir: str | Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    if not shutil.which("ffmpeg"):
        raise SilenceRenderError("ffmpeg não encontrado no PATH")
    source = Path(plan["source"]).resolve()
    if not source.is_file():
        raise SilenceRenderError(f"vídeo de origem não encontrado: {source}")
    keeps = [Interval(float(item["start_s"]), float(item["end_s"])) for item in plan.get("keep", [])]
    if not keeps:
        raise SilenceRenderError("o plano não contém nenhum trecho para manter")

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"{source.stem}__sem-silencios.mp4"
    plan_path = destination / f"{source.stem}__plano-silencios.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="roughcut_silence_") as temp:
        work = Path(temp)
        segments: list[Path] = []
        for index, keep in enumerate(keeps):
            segment = work / f"segment_{index:04d}.mp4"
            _run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{keep.start_s:.3f}", "-t", f"{keep.duration_s:.3f}",
                    "-i", str(source),
                    "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
                    "-ar", "44100", "-ac", "2", str(segment),
                ]
            )
            segments.append(segment)
            if on_progress:
                on_progress(index + 1, len(keeps))
        concat_file = work / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{segment}'\n" for segment in segments), encoding="utf-8"
        )
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
                "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output),
            ]
        )
    return output, plan_path
