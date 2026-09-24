from __future__ import annotations

import json
from pathlib import Path

from silence.analyze import probe_duration

from .audio import room_tone_region, speech_regions
from .cache import StageCache
from .config import load_rules
from .cuts import cuts_from_words
from .export import write_fcpxml, write_review_report, write_srt
from .retakes import detect_retakes
from .schema import Cut, CutPlan, SpeechRegion, Word
from .transcript import transcribe_words


def default_output_dir(input_dir: str | Path) -> Path:
    source = Path(input_dir).resolve()
    return source.parent / f"{source.name}__corte-inteligente"


def _load_words(value: list[dict]) -> list[Word]:
    return [Word(**item) for item in value]


def _load_regions(value: list[dict]) -> list[SpeechRegion]:
    return [SpeechRegion(**item) for item in value]


def analyze_clip(
    source: str | Path,
    output_dir: str | Path,
    *,
    preset: str = "colab",
    analysis_source: str | Path | None = None,
    protected_pauses: list[SpeechRegion] | None = None,
    refresh: bool = False,
) -> tuple[CutPlan, dict[str, Path]]:
    """Executa VAD/transcrição com cache e recalcula regras sem reusar modelo."""
    source = Path(source).resolve()
    audio_source = Path(analysis_source).resolve() if analysis_source else source
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache = StageCache(root / ".cache", source)
    duration = probe_duration(source)

    vad_cache = None if refresh else cache.load("vad")
    regions = _load_regions(vad_cache) if vad_cache is not None else speech_regions(audio_source)
    if vad_cache is None:
        cache.save("vad", [region.as_dict() for region in regions])

    transcript_cache = None if refresh else cache.load("transcript")
    words = _load_words(transcript_cache) if transcript_cache is not None else transcribe_words(audio_source)
    if transcript_cache is None:
        cache.save("transcript", [word.as_dict() for word in words])

    protected = protected_pauses or []
    rules = load_rules(preset)
    cuts = cuts_from_words(words, rules, protected)
    retakes = detect_retakes(words)
    for retake in retakes:
        if retake["selected"]:
            cuts.append(Cut(retake["start_s"], retake["end_s"], "retake_repetido", transcript_before=retake["text"], transcript_after=retake["kept_text"]))
    plan = CutPlan(str(source), duration, preset, words, sorted(cuts, key=lambda cut: cut.start_s), protected, retakes)
    artifacts = {
        "plan": root / "plans" / f"{source.stem}__corte.json",
        "srt": root / "subtitles" / f"{source.stem}__fala-cortada.srt",
        "report": root / "reports" / f"{source.stem}__revisao.md",
        "fcpxml": root / "timelines" / f"{source.stem}__timeline.fcpxml",
        "room_tone": root / "plans" / f"{source.stem}__room-tone.json",
    }
    for artifact in artifacts.values():
        artifact.parent.mkdir(parents=True, exist_ok=True)
    artifacts["plan"].write_text(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    write_srt(words, plan.cuts, artifacts["srt"])
    write_review_report(plan.cuts, retakes, artifacts["report"])
    write_fcpxml(source, duration, plan.cuts, artifacts["fcpxml"])
    room = room_tone_region(duration, regions)
    artifacts["room_tone"].write_text(json.dumps(room.as_dict() if room else None), encoding="utf-8")
    return plan, artifacts
