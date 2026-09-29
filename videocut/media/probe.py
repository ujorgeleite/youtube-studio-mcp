from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.safety import ensure_writable

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".webm"}
CAMERA_PROXY_EXTENSIONS = {".lrf"}
PROXY_DURATION_TOLERANCE_S = 1.0


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""


def require_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise MediaError(f"{binary} não encontrado no PATH")


def run_ffmpeg(args: list[str], *, output: str | Path, error: str) -> subprocess.CompletedProcess:
    """`-y` sobrescreve a saída; por isso ela é conferida contra a pasta de origem antes."""
    ensure_writable(output)
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args, str(output)], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        raise MediaError(f"{error}: {detail[-1] if detail else 'erro do ffmpeg'}")
    return proc


def list_videos(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise MediaError(f"pasta não encontrada: {root}")
    return sorted(
        (path for path in root.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and not path.name.startswith(".")),
        key=lambda path: path.name.lower(),
    )


def _fps(value: str | None) -> float:
    if not value or value in {"0/0", "0"}:
        return 0.0
    numerator, _, denominator = value.partition("/")
    return float(numerator) / float(denominator or 1) if float(denominator or 1) else 0.0


def _rotation(stream: dict) -> int:
    rotation = stream.get("tags", {}).get("rotate")
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            rotation = side["rotation"]
    return abs(int(float(rotation or 0))) % 180


def probe(path: str | Path) -> MediaInfo:
    """Dimensões já consideram a rotação gravada pelo celular."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise MediaError(f"ffprobe falhou em {Path(path).name}: {proc.stderr.strip()[:160]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError(f"{Path(path).name} não tem trilha de vídeo")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if _rotation(video) == 90:
        width, height = height, width
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return MediaInfo(
        duration_s=duration,
        width=width,
        height=height,
        fps=round(_fps(video.get("avg_frame_rate")) or _fps(video.get("r_frame_rate")), 3),
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        video_codec=video.get("codec_name", ""),
    )


def camera_proxy(path: str | Path, duration_s: float) -> Path | None:
    """Proxy gravado pela câmera (ex.: .LRF da DJI) com o mesmo nome e a mesma duração."""
    source = Path(path)
    for candidate in source.parent.iterdir():
        if candidate.stem != source.stem or candidate.suffix.lower() not in CAMERA_PROXY_EXTENSIONS:
            continue
        try:
            info = probe(candidate)
        except MediaError:
            return None
        return candidate if abs(info.duration_s - duration_s) <= PROXY_DURATION_TOLERANCE_S else None
    return None
