"""Frames para o modelo visual: poucos e bem distribuídos, nunca todos."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .probe import MediaError, run_ffmpeg

FRAME_WIDTH = 640
THUMB_WIDTH = 480
SCENE_THRESHOLD = 0.32
_PTS = re.compile(r"pts_time:([0-9.]+)")


def extract_frame(source: str | Path, at_s: float, destination: str | Path, width: int = FRAME_WIDTH) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ["-ss", f"{max(0.0, at_s):.3f}", "-i", str(source), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(target)],
        error=f"falha ao extrair frame de {Path(source).name}",
    )
    if not target.is_file():
        raise MediaError(f"frame não gerado em {at_s:.2f}s de {Path(source).name}")
    return target


def extract_thumbnail(source: str | Path, destination: str | Path, duration_s: float) -> Path:
    return extract_frame(source, min(max(duration_s * 0.2, 0.0), max(duration_s - 0.1, 0.0)), destination, THUMB_WIDTH)


def spread_times(start_s: float, end_s: float, count: int) -> list[float]:
    """Instantes no centro de `count` fatias iguais, evitando o primeiro e o último frame."""
    length = max(0.0, end_s - start_s)
    if count <= 0 or length <= 0:
        return [round(start_s, 3)] if count > 0 else []
    step = length / count
    return [round(start_s + step * (index + 0.5), 3) for index in range(count)]


def broad_sample_times(duration_s: float, every_s: float = 12.0, minimum: int = 3, maximum: int = 24) -> list[float]:
    count = min(maximum, max(minimum, int(duration_s // every_s)))
    return spread_times(0.0, duration_s, count)


def merge_times(base: list[float], extra: list[float], min_gap_s: float = 1.5) -> list[float]:
    merged: list[float] = []
    for moment in sorted([*base, *extra]):
        if not merged or moment - merged[-1] >= min_gap_s:
            merged.append(moment)
    return merged


def scene_changes(source: str | Path, threshold: float = SCENE_THRESHOLD, limit: int = 40) -> list[float]:
    """Mudanças visuais bruscas; indicam troca de plano, não troca de assunto."""
    hardware = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", *hardware, "-i", str(source), "-an", "-vf",
         f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise MediaError(f"falha ao detectar cenas de {Path(source).name}")
    times = [round(float(match), 3) for match in _PTS.findall(proc.stderr)]
    return times[:limit]


def extract_frames(source: str | Path, times: list[float], directory: str | Path, prefix: str, width: int = FRAME_WIDTH) -> list[tuple[float, Path]]:
    folder = Path(directory)
    frames = []
    for at in times:
        target = folder / f"{prefix}_{int(round(at * 1000)):09d}.jpg"
        if not target.is_file():
            extract_frame(source, at, target, width)
        frames.append((at, target))
    return frames
