"""Passo 1 — transcribe: roda Whisper local em cada clipe e formata o transcript.

Determinístico o suficiente, mas PESADO (baixa modelo, processa áudio) — por isso
os testes cobrem só a FORMATAÇÃO a partir de segmentos mockados, nunca a inferência.

Formato de saída consumido pelo passo 2 (order):

    [C01] arquivo=intro.mp4
    00:00:00–00:00:05 olá pessoal, hoje vamos falar sobre...
    00:00:05–00:00:11 o assunto de hoje é...

O import do faster-whisper é lazy (dentro da função) para que os testes e o
`--dry-run` funcionem sem a dependência pesada instalada/carregada.
"""

from __future__ import annotations

import os

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}
DEFAULT_MODEL_SIZE = "base"


def _seconds_to_tc(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_transcript(clip_id: str, filename: str, segments: list[dict]) -> str:
    """Formata segmentos {start, end, text} no bloco de transcript do clipe.

    Função pura — é o que os testes cobrem.
    """
    lines = [f"[{clip_id}] arquivo={filename}"]
    for seg in segments:
        start = _seconds_to_tc(seg["start"])
        end = _seconds_to_tc(seg["end"])
        text = str(seg.get("text", "")).strip()
        lines.append(f"{start}–{end} {text}")
    return "\n".join(lines)


def _run_whisper(path: str, model_size: str) -> list[dict]:
    """Chama o faster-whisper (import lazy). Substituível/mockável nos testes."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def transcribe_clip(
    path: str, clip_id: str, model_size: str = DEFAULT_MODEL_SIZE
) -> str:
    segments = _run_whisper(path, model_size)
    return format_transcript(clip_id, os.path.basename(path), segments)


def list_clips(input_dir: str) -> dict[str, str]:
    """Mapeia clip_id (C01, C02, ...) -> caminho, ordenado por nome de arquivo."""
    files = sorted(
        f
        for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in VIDEO_EXTS
    )
    return {
        f"C{idx:02d}": os.path.join(input_dir, name)
        for idx, name in enumerate(files, start=1)
    }


def transcribe_folder(
    input_dir: str, model_size: str = DEFAULT_MODEL_SIZE
) -> tuple[str, dict[str, str]]:
    """Transcreve todos os clipes da pasta.

    Retorna (transcripts_concatenados, clip_map).
    """
    clip_map = list_clips(input_dir)
    if not clip_map:
        raise FileNotFoundError(f"nenhum clipe de vídeo em {input_dir}")
    blocks = [
        transcribe_clip(path, clip_id, model_size)
        for clip_id, path in clip_map.items()
    ]
    return "\n\n".join(blocks), clip_map
