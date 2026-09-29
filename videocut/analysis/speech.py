"""Transcrição local com timestamps por palavra e frases prontas para citar."""

from __future__ import annotations

import gc
import re
from pathlib import Path

from core.cache import StageCache, fingerprint
from core.config import glossary, models
from core.schema import Sentence, Transcript, Word
from core.serial import from_data

SENTENCE_END = re.compile(r"[.!?…]+[\"”')]*$")
MAX_SENTENCE_S = 18.0
PAUSE_SPLIT_S = 0.9


class SpeechError(RuntimeError):
    pass


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    stripped = text.strip()
    core = stripped.strip(".,!?…;:\"'”“()").lower()
    replacement = corrections.get(core)
    return stripped.replace(stripped.strip(".,!?…;:\"'”“()"), replacement, 1) if replacement else stripped


def words_from_result(result: dict, corrections: dict[str, str]) -> list[Word]:
    words = []
    for segment in result.get("segments", []):
        for row in segment.get("words") or []:
            start, end = row.get("start"), row.get("end")
            text = apply_corrections(str(row.get("word", "")), corrections)
            if start is None or end is None or not text:
                continue
            words.append(Word(round(float(start), 3), round(float(end), 3), text, row.get("probability")))
    return words


def group_sentences(words: list[Word]) -> list[Sentence]:
    """Frases terminam em pontuação, pausa longa ou limite de duração; cortes nunca caem no meio."""
    sentences: list[Sentence] = []
    current: list[Word] = []

    def close() -> None:
        if current:
            sentences.append(Sentence(current[0].start_s, current[-1].end_s, " ".join(word.text for word in current)))
            current.clear()

    for word in words:
        if current and (word.start_s - current[-1].end_s >= PAUSE_SPLIT_S or word.end_s - current[0].start_s > MAX_SENTENCE_S):
            close()
        current.append(word)
        if SENTENCE_END.search(word.text):
            close()
    close()
    return sentences


def transcribe_audio(audio: str | Path, model: str) -> dict:
    try:
        import mlx_whisper
    except ImportError as error:
        raise SpeechError("mlx-whisper não instalado") from error
    settings = glossary()
    return mlx_whisper.transcribe(
        str(audio), path_or_hf_repo=model, language=settings.get("language", "pt"),
        initial_prompt=settings.get("initial_prompt"), word_timestamps=True, verbose=None,
        condition_on_previous_text=False,
    )


def release_model() -> None:
    """Libera o Whisper da memória unificada antes de carregar o modelo visual."""
    try:
        from mlx_whisper.transcribe import ModelHolder
        import mlx.core as mx
    except ImportError:
        return
    ModelHolder.model = None
    ModelHolder.model_path = None
    gc.collect()
    mx.clear_cache()


def transcribe_take(
    take_id: str,
    source: str | Path,
    audio: str | Path,
    cache_root: str | Path,
    *,
    model: str | None = None,
    refresh: bool = False,
) -> Transcript:
    repo = model or models().get("whisper", "mlx-community/whisper-large-v3-turbo")
    settings = glossary()
    variant = fingerprint(repo, settings.get("initial_prompt"), sorted(settings.get("corrections", {}).items()))
    cache = StageCache(cache_root, source)
    cached = None if refresh else cache.load("transcript", variant)
    if cached is not None:
        transcript = from_data(Transcript, cached)
        transcript.take_id = take_id
        return transcript
    words = words_from_result(transcribe_audio(audio, repo), settings.get("corrections", {}))
    transcript = Transcript(take_id, settings.get("language", "pt"), words, group_sentences(words))
    cache.save("transcript", transcript, variant)
    return transcript
