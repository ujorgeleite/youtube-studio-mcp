from __future__ import annotations

import json
import subprocess
from pathlib import Path


class PreprocessError(RuntimeError):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise PreprocessError(result.stderr.strip() or "ffmpeg falhou")
    return result


def extract_audio(source: str | Path, destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "48000", str(target)])
    return target


def _loudnorm_stats(stderr: str) -> dict:
    start, end = stderr.rfind("{"), stderr.rfind("}")
    if start < 0 or end < start:
        raise PreprocessError("ffmpeg não retornou estatísticas loudnorm")
    return json.loads(stderr[start:end + 1])


def normalize_loudness(source: str | Path, destination: str | Path, target_lufs: float = -14.0) -> Path:
    """Normalização EBU R128 em duas passadas, apropriada para saída do YouTube."""
    first = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(source), "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if first.returncode != 0:
        raise PreprocessError(first.stderr.strip())
    stats = _loudnorm_stats(first.stderr)
    filter_value = (
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:measured_I={stats['input_i']}:"
        f"measured_LRA={stats['input_lra']}:measured_TP={stats['input_tp']}:"
        f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true:print_format=summary"
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", filter_value, "-c:a", "aac", str(target)])
    return target
