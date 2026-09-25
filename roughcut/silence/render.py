"""Renderiza um plano de remoção sem modificar o vídeo de origem."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
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


@lru_cache
def _video_encoder_args() -> list[str]:
    """Prefere o encoder de hardware nativo do macOS, com fallback portátil."""
    if platform.system() == "Darwin":
        available = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, check=False
        ).stdout
        if "h264_videotoolbox" in available:
            # A escala/fps já são definidos pelo filtro. A taxa mantém qualidade
            # adequada para importar no editor sem consumir CPU no x264.
            return ["-c:v", "h264_videotoolbox", "-b:v", "10M", "-maxrate", "12M", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]


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
    output_prefix = str(plan.get("render_options", {}).get("output_prefix", ""))
    output = destination / f"{output_prefix}{source.stem}__sem-silencios.mp4"
    removed_s = max(0.0, float(plan.get("duration_s", 0)) - sum(item.duration_s for item in keeps))
    options = plan.get("render_options", {})
    removed_pct = 100 * removed_s / float(plan.get("duration_s", 1) or 1)
    should_copy = (
        not options.get("always_render", False)
        and (removed_s < float(options.get("min_removed_s", 1.0))
             or removed_pct < float(options.get("min_removed_pct", 0.25)))
    )
    if should_copy:
        shutil.copy2(source, output)
        plan["render"] = {
            "strategy": "copy_original",
            "reason": "remocao_abaixo_do_limite",
            "removed_s": round(removed_s, 3),
            "removed_pct": round(removed_pct, 3),
        }
    else:
        filters: list[str] = []
        streams: list[str] = []
        for index, keep in enumerate(keeps):
            filters.extend(
                [
                    f"[0:v]trim=start={keep.start_s:.3f}:end={keep.end_s:.3f},setpts=PTS-STARTPTS,"
                    "scale=1280:720:force_original_aspect_ratio=decrease,"
                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p[v" + str(index) + "]",
                    f"[0:a]atrim=start={keep.start_s:.3f}:end={keep.end_s:.3f},asetpts=PTS-STARTPTS[a{index}]",
                ]
            )
            streams.extend([f"[v{index}]", f"[a{index}]"])
        filters.append("".join(streams) + f"concat=n={len(keeps)}:v=1:a=1[v][a]")
        if on_progress:
            on_progress(0, len(keeps))
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                *_video_encoder_args(), "-c:a", "aac",
                "-ar", "44100", "-ac", "2", output,
            ]
        )
        if on_progress:
            on_progress(len(keeps), len(keeps))
        plan["render"] = {
            "strategy": "single_pass_ffmpeg",
            "removed_s": round(removed_s, 3),
            "removed_pct": round(removed_pct, 3),
        }
    plan_path = destination / f"{source.stem}__plano-silencios.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return output, plan_path
