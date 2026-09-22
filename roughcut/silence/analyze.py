"""Detecção de silêncio e forma de onda usando os binários do sistema."""

from __future__ import annotations

import json
import os
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


def probe_media(path: str | Path) -> tuple[float, bool]:
    """Retorna duração e presença de áudio para validar proxies DJI."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"ffprobe falhou em {path}: {proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout)
        return float(data["format"]["duration"]), any(
            stream.get("codec_type") == "audio" for stream in data.get("streams", [])
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SilenceAnalysisError(f"metadados inválidos para {path}") from exc


def resolve_analysis_source(path: str | Path, *, use_lrf_proxy: bool = True) -> tuple[Path, str, float]:
    """Prefere proxy DJI válido para análise; o render sempre usa o original."""
    original = Path(path).expanduser().resolve()
    if not use_lrf_proxy:
        return original, "original", 0.0
    proxy = original.with_suffix(".LRF")
    if not proxy.is_file():
        return original, "original", 0.0
    original_duration, _ = probe_media(original)
    proxy_duration, has_audio = probe_media(proxy)
    delta = proxy_duration - original_duration
    tolerance = max(0.25, original_duration * 0.005)
    if not has_audio or abs(delta) > tolerance:
        return original, "original", 0.0
    return proxy, "dji_lrf_proxy", delta


def extract_thumbnail(
    path: str | Path,
    destination: str | Path,
    *,
    duration_s: float | None = None,
) -> Path:
    """Extrai um frame representativo sem alterar o vídeo de origem."""
    duration = duration_s if duration_s is not None else probe_duration(path)
    at_s = min(max(duration * 0.1, 0.0), max(0.0, duration - 0.05))
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{at_s:.3f}", "-i", str(path), "-frames:v", "1",
            "-vf", "scale=320:180:force_original_aspect_ratio=decrease,"
            "pad=320:180:(ow-iw)/2:(oh-ih)/2", str(target),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not target.is_file():
        raise SilenceAnalysisError(f"não foi possível gerar miniatura de {path}")
    return target


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
            "-vn",
            "-af", f"silencedetect=noise={settings.noise_db}dB:d={settings.min_silence_s}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"análise falhou em {path}: {proc.stderr.strip()}")
    return duration_s, parse_silencedetect(proc.stderr, duration_s)


def analyze_audio_once(
    path: str | Path, settings: SilenceSettings, max_points: int = 900
) -> tuple[float, list[Interval], list[float]]:
    """Detecta silêncios e coleta a forma de onda em uma só decodificação de áudio."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SilenceAnalysisError("ffmpeg e ffprobe precisam estar instalados no PATH")
    duration_s = probe_duration(path)
    filter_graph = (
        "[0:a]asplit=2[detect][wave];"
        f"[detect]silencedetect=noise={settings.noise_db}dB:d={settings.min_silence_s}[detected];"
        "[wave]aformat=channel_layouts=mono,aresample=200[waveform]"
    )
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
            "-filter_complex", filter_graph,
            "-map", "[detected]", "-f", "null", os.devnull,
            "-map", "[waveform]", "-f", "s16le", "pipe:1",
        ],
        capture_output=True,
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise SilenceAnalysisError(f"análise falhou em {path}: {stderr.strip()}")
    count = len(proc.stdout) // 2
    if count == 0:
        waveform: list[float] = []
    else:
        samples = struct.unpack(f"<{count}h", proc.stdout[: count * 2])
        bucket = max(1, (count + max_points - 1) // max_points)
        waveform = [
            round(max(abs(value) for value in samples[index : index + bucket]) / 32768, 4)
            for index in range(0, count, bucket)
        ]
    return duration_s, parse_silencedetect(stderr, duration_s), waveform


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


def analyze_video(
    path: str | Path,
    settings: SilenceSettings | None = None,
    *,
    use_lrf_proxy: bool = True,
) -> VideoAnalysis:
    selected = settings or SilenceSettings()
    original = Path(path).resolve()
    analysis_path, source_kind, delta = resolve_analysis_source(
        original, use_lrf_proxy=use_lrf_proxy
    )
    duration_s, silences, waveform = analyze_audio_once(analysis_path, selected)
    return VideoAnalysis(
        source=str(original),
        duration_s=duration_s,
        silences=silences,
        waveform=waveform,
        settings=selected,
        analysis_source=str(analysis_path),
        analysis_source_kind=source_kind,
        analysis_duration_delta_s=delta,
    )
