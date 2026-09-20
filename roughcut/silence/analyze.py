"""Detecção de silêncio e forma de onda usando os binários do sistema."""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

from .schema import Interval, SilenceSettings, VideoAnalysis

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}
_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


class SilenceAnalysisError(RuntimeError):
    pass


def list_videos(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise SilenceAnalysisError(f"pasta não encontrada: {root}")
    return sorted(
        (path for path in root.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda path: path.name.lower(),
    )


def probe_duration(path: str | Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"ffprobe falhou em {path}: {proc.stderr.strip()}")
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SilenceAnalysisError(f"duração inválida para {path}") from exc


def parse_silencedetect(log: str, duration_s: float) -> list[Interval]:
    intervals: list[Interval] = []
    pending_start: float | None = None
    for line in log.splitlines():
        start = _START_RE.search(line)
        if start:
            pending_start = max(0.0, float(start.group(1)))
        end = _END_RE.search(line)
        if end:
            end_s = min(duration_s, float(end.group(1)))
            start_s = pending_start if pending_start is not None else 0.0
            if end_s > start_s:
                intervals.append(Interval(start_s, end_s))
            pending_start = None
    if pending_start is not None and duration_s > pending_start:
        intervals.append(Interval(pending_start, duration_s))
    return intervals


def detect_silences(path: str | Path, settings: SilenceSettings) -> tuple[float, list[Interval]]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SilenceAnalysisError("ffmpeg e ffprobe precisam estar instalados no PATH")
    duration_s = probe_duration(path)
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"silencedetect=noise={settings.noise_db}dB:d={settings.min_silence_s}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"análise falhou em {path}: {proc.stderr.strip()}")
    return duration_s, parse_silencedetect(proc.stderr, duration_s)


def extract_waveform(path: str | Path, max_points: int = 900) -> list[float]:
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
            "-ar", "200", "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"não foi possível gerar a forma de onda de {path}")
    count = len(proc.stdout) // 2
    if count == 0:
        return []
    samples = struct.unpack(f"<{count}h", proc.stdout[: count * 2])
    bucket = max(1, (count + max_points - 1) // max_points)
    peaks = [max(abs(value) for value in samples[i : i + bucket]) / 32768 for i in range(0, count, bucket)]
    return [round(value, 4) for value in peaks]


def analyze_video(path: str | Path, settings: SilenceSettings | None = None) -> VideoAnalysis:
    selected = settings or SilenceSettings()
    duration_s, silences = detect_silences(path, selected)
    return VideoAnalysis(
        source=str(Path(path).resolve()),
        duration_s=duration_s,
        silences=silences,
        waveform=extract_waveform(path),
        settings=selected,
    )

