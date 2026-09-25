"""Transforma os silêncios detectados em blocos de diálogo e cortes."""

from __future__ import annotations

from .schema import Interval, SilenceSettings, VideoAnalysis

MODES = {
    "around_dialogues": "Limpar ao redor dos diálogos",
    "all": "Remover todos os silêncios",
    "cautious": "Remoção cautelosa",
}


def _clamp(interval: Interval, duration_s: float) -> Interval:
    return Interval(max(0.0, interval.start_s), min(duration_s, interval.end_s))


def _merge(intervals: list[Interval], gap_s: float = 0.0) -> list[Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item.start_s)
    merged = [Interval(ordered[0].start_s, ordered[0].end_s)]
    for item in ordered[1:]:
        tail = merged[-1]
        if item.start_s <= tail.end_s + gap_s:
            tail.end_s = max(tail.end_s, item.end_s)
        else:
            merged.append(Interval(item.start_s, item.end_s))
    return merged


def speech_intervals(duration_s: float, silences: list[Interval]) -> list[Interval]:
    speech: list[Interval] = []
    cursor = 0.0
    for silence in _merge([_clamp(item, duration_s) for item in silences]):
        if silence.start_s > cursor:
            speech.append(Interval(cursor, silence.start_s))
        cursor = max(cursor, silence.end_s)
    if cursor < duration_s:
        speech.append(Interval(cursor, duration_s))
    return [item for item in speech if item.duration_s > 0.01]


def dialogue_blocks(analysis: VideoAnalysis) -> list[Interval]:
    settings = analysis.settings
    speech = speech_intervals(analysis.duration_s, analysis.silences)
    return _merge(speech, settings.dialogue_merge_gap_s)


def _padded(intervals: list[Interval], duration_s: float, settings: SilenceSettings) -> list[Interval]:
    return _merge(
        [
            Interval(
                max(0.0, item.start_s - settings.padding_before_s),
                min(duration_s, item.end_s + settings.padding_after_s),
            )
            for item in intervals
        ]
    )


def build_keep_intervals(analysis: VideoAnalysis, mode: str) -> list[Interval]:
    if mode not in MODES:
        raise ValueError(f"modo de silêncio desconhecido: {mode}")
    settings = analysis.settings
    if mode == "around_dialogues":
        return _padded(dialogue_blocks(analysis), analysis.duration_s, settings)
    if mode == "all":
        return _padded(speech_intervals(analysis.duration_s, analysis.silences), analysis.duration_s, settings)

    removals: list[Interval] = []
    preserve = settings.cautious_preserved_pause_s
    for silence in analysis.silences:
        leading = silence.start_s <= 0.01
        trailing = silence.end_s >= analysis.duration_s - 0.01
        if leading:
            removals.append(Interval(0.0, max(0.0, silence.end_s - settings.padding_before_s)))
        elif trailing:
            removals.append(Interval(min(analysis.duration_s, silence.start_s + settings.padding_after_s), analysis.duration_s))
        elif silence.duration_s >= settings.cautious_internal_threshold_s:
            removable = silence.duration_s - preserve
            if removable > 0:
                left = silence.start_s + preserve / 2
                removals.append(Interval(left, left + removable))
    return complement(analysis.duration_s, removals)


def complement(duration_s: float, removals: list[Interval]) -> list[Interval]:
    keeps: list[Interval] = []
    cursor = 0.0
    for removal in _merge([_clamp(item, duration_s) for item in removals]):
        if removal.start_s > cursor:
            keeps.append(Interval(cursor, removal.start_s))
        cursor = max(cursor, removal.end_s)
    if cursor < duration_s:
        keeps.append(Interval(cursor, duration_s))
    return [item for item in keeps if item.duration_s > 0.01]


def plan_for(analysis: VideoAnalysis, mode: str, keeps: list[Interval] | None = None) -> dict:
    selected = keeps if keeps is not None else build_keep_intervals(analysis, mode)
    dialogues = dialogue_blocks(analysis)
    return {
        "version": 1,
        "source": analysis.source,
        "mode": mode,
        "duration_s": round(analysis.duration_s, 3),
        "settings": analysis.as_dict()["settings"],
        "silences": [item.as_dict() for item in analysis.silences],
        "dialogues": [
            {"id": f"D{index:03d}", **item.as_dict(), "selected": True}
            for index, item in enumerate(dialogues, 1)
        ],
        "keep": [item.as_dict() for item in selected],
        "estimated_output_duration_s": round(sum(item.duration_s for item in selected), 3),
        "render_options": {
            "min_removed_s": 1.0,
            "min_removed_pct": 0.25,
            "always_render": False,
        },
    }
