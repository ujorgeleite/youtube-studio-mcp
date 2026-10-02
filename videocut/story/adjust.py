"""Ajustes instantâneos de uma proposta, sem chamar modelo."""

from __future__ import annotations

import copy

from core.schema import SPEECH, Beat, Inventory, Moment, StoryVideo

from .validate import ReportBuilder

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


def shorten(video: StoryVideo, target_s: float, inventory: Inventory, excluded: set[str] | None = None,
            protected: set[str] | None = None) -> StoryVideo:
    """Tira blocos de menor prioridade e depois apara frases finais até caber no alvo.

    Blocos protegidos na revisão nunca saem nem são aparados.
    """
    result = copy.deepcopy(video)
    skip = excluded or set()
    keep = protected or set()
    active = [beat for beat in result.beats if beat.id not in skip]
    excess = sum(beat.duration_s for beat in active) - target_s
    candidates = sorted(
        (beat for beat in active if beat.role not in PROTECTED_ROLES and beat.id not in keep),
        key=lambda beat: (DROP_ORDER.get(beat.role, 1), -beat.duration_s),
    )
    for beat in candidates:
        if excess <= 0 or len(active) <= MIN_ACTIVE_BEATS:
            break
        active.remove(beat)
        result.beats.remove(beat)
        excess -= beat.duration_s
    if excess > 0:
        _trim_last_sentences([beat for beat in active if beat.id not in keep], inventory, excess)
    return result


def _sentences(beat: Beat, inventory: Inventory) -> list:
    transcript = inventory.transcripts.get(beat.take_id)
    return transcript.sentences if transcript else []


def extend_beat(beat: Beat, inventory: Inventory) -> bool:
    """Inclui a próxima frase do mesmo take; devolve False se não houver."""
    following = [s for s in _sentences(beat, inventory) if s.start_s >= beat.end_s - 0.3]
    take = inventory.take(beat.take_id)
    if beat.audio != SPEECH or not following:
        return False
    beat.end_s = round(min(following[0].end_s + 0.25, take.duration_s if take else following[0].end_s + 0.25), 3)
    _refresh_evidence(beat, inventory)
    return True


def trim_beat(beat: Beat, inventory: Inventory) -> bool:
    """Remove a última frase, mantendo ao menos uma."""
    inside = [s for s in _sentences(beat, inventory) if s.start_s >= beat.start_s - 0.2 and s.end_s <= beat.end_s + 0.3]
    if beat.audio != SPEECH or len(inside) < 2:
        return False
    beat.end_s = round(inside[-2].end_s + 0.25, 3)
    _fit_overlays(beat)
    _refresh_evidence(beat, inventory)
    return True


def _refresh_evidence(beat: Beat, inventory: Inventory) -> None:
    builder = ReportBuilder(inventory)
    moment = next((m for m in inventory.moments if m.take_id == beat.take_id and m.start_s <= beat.start_s + 0.5 <= m.end_s), None)
    if moment:
        beat.evidence = [builder.evidence_for(moment, beat.start_s, beat.end_s)]


def replace_moment(beat: Beat, moment: Moment, inventory: Inventory) -> None:
    """Troca o trecho do bloco por outro momento real, com cortes em frases inteiras."""
    builder = ReportBuilder(inventory)
    start, end = moment.start_s, moment.end_s
    beat.audio = SPEECH if moment.speech else "ambiente"
    if beat.audio == SPEECH:
        start, end = builder.snap_to_sentences(moment.take_id, start, end)
    beat.take_id, beat.start_s, beat.end_s = moment.take_id, round(start, 3), round(end, 3)
    beat.evidence = [builder.evidence_for(moment, start, end)]
    _fit_overlays(beat)
