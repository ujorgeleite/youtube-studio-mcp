from __future__ import annotations

from pathlib import Path

from .probe import MediaError, run_ffmpeg

PROXY_HEIGHT = 540


def extract_speech_audio(source: str | Path, destination: str | Path) -> Path:
    """WAV mono 16 kHz, o formato que o Whisper consome sem reamostrar."""
    target = Path(destination)
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)],
               error=f"falha ao extrair áudio de {Path(source).name}")
    if not target.is_file():
        raise MediaError(f"áudio não gerado para {Path(source).name}")
    return target


def make_proxy(source: str | Path, destination: str | Path, height: int = PROXY_HEIGHT) -> Path:
    """H.264 leve para o player do navegador; HEVC/ProRes não tocam em todo navegador."""
    target = Path(destination)
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}")
    run_ffmpeg(
        ["-i", str(source), "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-f", "mp4", str(temporary)],
        error=f"falha ao criar proxy de {Path(source).name}",
    )
    temporary.replace(target)
    return target
