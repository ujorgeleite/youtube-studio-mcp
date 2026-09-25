from __future__ import annotations

from pathlib import Path

from .config import apply_glossary, load_glossary
from .schema import Word

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class TranscriptError(RuntimeError):
    pass


def _word_rows(result: dict) -> list[dict]:
    rows: list[dict] = []
    for segment in result.get("segments", []):
        rows.extend(segment.get("words") or [])
    return rows


def normalize_words(rows: list[dict], corrections: dict[str, str]) -> list[Word]:
    words = []
    for row in rows:
        start, end = row.get("start"), row.get("end")
        if start is None or end is None:
            continue
        text = apply_glossary(str(row.get("word", "")).strip(), corrections)
        if text:
            words.append(Word(float(start), float(end), text, row.get("probability")))
    return words


def transcribe_words(
    source: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    glossary: dict | None = None,
) -> list[Word]:
    """Transcreve localmente com MLX/Metal e devolve timestamps por palavra."""
    try:
        import mlx_whisper
    except ImportError as exc:
        raise TranscriptError("mlx-whisper não instalado") from exc
    data = glossary or load_glossary()
    result = mlx_whisper.transcribe(
        str(source), path_or_hf_repo=model, language=data.get("language", "pt"),
        initial_prompt=data.get("initial_prompt"), word_timestamps=True, verbose=False,
    )
    return normalize_words(_word_rows(result), data.get("corrections", {}))
