from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .schema import SpeechRegion


class AudioError(RuntimeError):
    pass


def _extract_mono_16k(source: str | Path, destination: str | Path) -> None:
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
            "-vn", "-ac", "1", "-ar", "16000", str(destination),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AudioError(proc.stderr.strip() or f"falha ao extrair áudio de {source}")


def speech_regions(
    source: str | Path,
    *,
    threshold: float = 0.5,
    min_speech_ms: int = 250,
    min_silence_ms: int = 200,
) -> list[SpeechRegion]:
    """Mapeia fala com Silero VAD; nunca decide corte por volume bruto."""
    if not shutil.which("ffmpeg"):
        raise AudioError("ffmpeg não encontrado")
    try:
        from silero_vad import get_speech_timestamps, load_silero_vad
    except ImportError as exc:
        raise AudioError("silero-vad não instalado") from exc
    with tempfile.TemporaryDirectory(prefix="roughcut_vad_") as directory:
        wav = Path(directory) / "audio.wav"
        _extract_mono_16k(source, wav)
        model = load_silero_vad()
        with wave.open(str(wav), "rb") as handle:
            if handle.getframerate() != 16000 or handle.getnchannels() != 1:
                raise AudioError("WAV do VAD deve ser mono a 16 kHz")
            samples = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype("float32") / 32768
        import torch
        audio = torch.from_numpy(samples)
        stamps = get_speech_timestamps(
            audio, model, sampling_rate=16000, threshold=threshold,
            min_speech_duration_ms=min_speech_ms, min_silence_duration_ms=min_silence_ms,
        )
    return [SpeechRegion(item["start"] / 16000, item["end"] / 16000) for item in stamps]


def room_tone_region(duration_s: float, regions: list[SpeechRegion], seconds: float = 10.0) -> SpeechRegion | None:
    """Maior janela sem voz, limitada a `seconds`, para preencher cortes depois."""
    cursor = 0.0
    best: SpeechRegion | None = None
    for region in [*regions, SpeechRegion(duration_s, duration_s)]:
        if region.start_s > cursor:
            candidate = SpeechRegion(cursor, min(region.start_s, cursor + seconds))
            if best is None or candidate.end_s - candidate.start_s > best.end_s - best.start_s:
                best = candidate
        cursor = max(cursor, region.end_s)
    return best
