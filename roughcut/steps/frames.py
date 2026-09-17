"""Extração de frames (ffmpeg) para caça de ganchos — determinístico.

Duas fontes: uma grade de thumbnails de cada clipe bruto (visão geral) e os frames
dos clipes que a ordenação colocou no beat cold_open (o gancho do formato).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from steps.assemble import parse_timecode

THUMB_WIDTH = 480
GRID_EVERY_SECONDS = 5.0
GRID_MAX_PER_CLIP = 8


class FramesError(RuntimeError):
    pass


def _probe_duration(src: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", src],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise FramesError("ffprobe não encontrado (vem com o ffmpeg)") from exc
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _timestamps(duration: float, every: float, limit: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    stamps = []
    moment = 0.0
    while moment < duration and len(stamps) < limit:
        stamps.append(round(moment, 3))
        moment += every
    return stamps or [0.0]


def extract_frame(src: str, at_seconds: float, dest: str, width: int = THUMB_WIDTH) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{max(0.0, at_seconds):.3f}", "-i", src,
         "-frames:v", "1", "-vf", f"scale={width}:-1", dest],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not os.path.exists(dest):
        raise FramesError(f"falha ao extrair frame de {src}: {proc.stderr.strip()}")


def grid_frames(
    clip_map: dict[str, str],
    out_dir: str,
    every_seconds: float = GRID_EVERY_SECONDS,
    max_per_clip: int = GRID_MAX_PER_CLIP,
) -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    for clip_id, src in clip_map.items():
        stamps = _timestamps(_probe_duration(src), every_seconds, max_per_clip)
        for index, at in enumerate(stamps):
            name = f"grid_{clip_id}_{index:02d}.jpg"
            extract_frame(src, at, str(out / name))
            frames.append({"clip_id": clip_id, "at_s": at, "path": name, "kind": "grid"})
    return frames


def cold_open_frames(cut_list: dict, clip_map: dict[str, str], out_dir: str) -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames = []
    for beat in cut_list.get("roughcut", []):
        if beat.get("beat") != "cold_open":
            continue
        for index, clip in enumerate(beat.get("clips") or []):
            clip_id = clip.get("clip_id")
            src = clip_map.get(clip_id)
            if not src:
                continue
            middle = (parse_timecode(clip.get("in", "0")) + parse_timecode(clip.get("out", "0"))) / 2
            name = f"hook_{clip_id}_{index:02d}.jpg"
            extract_frame(src, middle, str(out / name))
            frames.append(
                {
                    "clip_id": clip_id,
                    "in": clip.get("in"),
                    "out": clip.get("out"),
                    "at_s": round(middle, 2),
                    "path": name,
                    "kind": "cold_open",
                }
            )
    return frames
