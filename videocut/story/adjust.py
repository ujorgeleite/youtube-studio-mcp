"""Ajustes instantâneos de uma proposta, sem chamar modelo."""

from __future__ import annotations

import copy

from core.schema import SPEECH, Beat, Inventory, StoryVideo

PROTECTED_ROLES = {"gancho", "mensagem", "conclusao"}
DROP_ORDER = {"apoio": 0, "desenvolvimento": 1, "contexto": 2}
MIN_ACTIVE_BEATS = 2


def _fit_overlays(beat: Beat) -> None:
    beat.overlays = [overlay for overlay in beat.overlays if overlay.at_s + 0.5 < beat.duration_s]
    for overlay in beat.overlays:
        overlay.end_s = round(min(overlay.end_s, overlay.start_s + beat.duration_s - overlay.at_s), 3)


def _trim_last_sentences(beats: list[Beat], inventory: Inventory, excess_s: float) -> float:
    """Remove frases finais dos blocos de fala mais longos, mantendo ao menos uma."""
    for beat in sorted(beats, key=lambda beat: -beat.duration_s):
        transcript = inventory.transcripts.get(beat.take_id)
        if excess_s <= 0 or beat.audio != SPEECH or not transcript:
            continue
        inside = [s for s in transcript.sentences if s.start_s >= beat.start_s - 0.2 and s.end_s <= beat.end_s + 0.3]
        while len(inside) > 1 and excess_s > 0:
            inside.pop()
            new_end = min(beat.end_s, inside[-1].end_s + 0.25)
            excess_s -= beat.end_s - new_end
            beat.end_s = round(new_end, 3)
        _fit_overlays(beat)
    return excess_s


def shorten(video: StoryVideo, target_s: float, inventory: Inventory, excluded: set[str] | None = None) -> StoryVideo:
    """Tira blocos de menor prioridade e depois apara frases finais até caber no alvo."""
    result = copy.deepcopy(video)
    skip = excluded or set()
    active = [beat for beat in result.beats if beat.id not in skip]
    excess = sum(beat.duration_s for beat in active) - target_s
    candidates = sorted(
        (beat for beat in active if beat.role not in PROTECTED_ROLES),
        key=lambda beat: (DROP_ORDER.get(beat.role, 1), -beat.duration_s),
    )
    for beat in candidates:
        if excess <= 0 or len(active) <= MIN_ACTIVE_BEATS:
            break
        active.remove(beat)
        result.beats.remove(beat)
        excess -= beat.duration_s
    if excess > 0:
        _trim_last_sentences(active, inventory, excess)
    return result
