"""Critérios de suficiência verificáveis sem modelo: presença e papel dos blocos."""

from __future__ import annotations

from core.schema import (
    CRITERION_MISSING, CRITERION_OK, CRITERION_REVIEW, SPEECH, Criterion, Proposal, StoryVideo,
)

SEVERITY = {CRITERION_OK: 0, CRITERION_REVIEW: 1, CRITERION_MISSING: 2}
OPENING_ROLES = {"gancho", "contexto"}
CLOSING_ROLES = {"conclusao", "mensagem"}
MIDDLE_ROLES = {"contexto", "desenvolvimento", "apoio"}


def worst(first: str, second: str) -> str:
    return first if SEVERITY.get(first, 1) >= SEVERITY.get(second, 1) else second


def _opening(videos: list[StoryVideo]) -> tuple[str, str]:
    for video in videos:
        if not video.beats:
            return CRITERION_MISSING, f"{video.title} não tem blocos."
        if video.beats[0].role not in OPENING_ROLES:
            return CRITERION_REVIEW, f"{video.title} começa por “{video.beats[0].title}”; confira se prende nos primeiros segundos."
    return CRITERION_OK, ""


def _message(videos: list[StoryVideo]) -> tuple[str, str]:
    beats = [beat for video in videos for beat in video.beats]
    if not any(beat.audio == SPEECH for beat in beats):
        return CRITERION_MISSING, "Nenhuma fala sustenta a mensagem; imagens sozinhas não bastam."
    if not any(beat.role == "mensagem" and beat.audio == SPEECH for beat in beats):
        return CRITERION_REVIEW, "Há falas, mas nenhum bloco foi marcado como a mensagem central."
    return CRITERION_OK, ""


def _development(videos: list[StoryVideo]) -> tuple[str, str]:
    for video in videos:
        if len(video.beats) < 3 or not any(beat.role in MIDDLE_ROLES for beat in video.beats):
            return CRITERION_REVIEW, f"{video.title} tem pouco desenvolvimento entre abertura e fechamento."
    return CRITERION_OK, ""


def _closing(videos: list[StoryVideo]) -> tuple[str, str]:
    for video in videos:
        if not any(beat.role == "conclusao" for beat in video.beats):
            return CRITERION_REVIEW, f"{video.title} não tem conclusão explícita."
    return CRITERION_OK, ""


def _coverage(videos: list[StoryVideo]) -> tuple[str, str]:
    for video in videos:
        speech_s = sum(beat.duration_s for beat in video.beats if beat.audio == SPEECH)
        visual_takes = {beat.take_id for beat in video.beats} | {overlay.take_id for beat in video.beats for overlay in beat.overlays}
        if speech_s > 25 and len(visual_takes) < 2:
            return CRITERION_REVIEW, f"{video.title} usa imagens de um único take; faltam planos para variar."
    return CRITERION_OK, ""


def _independence(videos: list[StoryVideo]) -> tuple[str, str]:
    for video in videos:
        if not video.beats or video.beats[0].role not in OPENING_ROLES or video.beats[-1].role not in CLOSING_ROLES:
            return CRITERION_REVIEW, f"{video.title} pode não funcionar sozinho: confira abertura e fechamento próprios."
    return CRITERION_OK, ""


CHECKS = {
    "mensagem": _message,
    "abertura": _opening,
    "desenvolvimento": _development,
    "encerramento": _closing,
    "cobertura_visual": _coverage,
    "independencia": _independence,
}


def assess(proposal: Proposal, suggested: dict[str, Criterion]) -> list[Criterion]:
    """Combina o julgamento do modelo com a checagem estrutural; vale o mais severo."""
    result = []
    for key, check in CHECKS.items():
        if key == "independencia" and not proposal.multiple:
            continue
        status, detail = check(proposal.videos)
        given = suggested.get(key)
        if given is None:
            result.append(Criterion(key, status, detail))
            continue
        final = worst(given.status, status)
        text = given.detail if SEVERITY[given.status] >= SEVERITY[status] else " ".join(part for part in (detail, given.detail) if part)
        result.append(Criterion(key, final, text, given.evidence))
    return result


def is_partial(criteria: list[Criterion]) -> bool:
    essentials = {"mensagem", "abertura"}
    return any(criterion.key in essentials and criterion.status == CRITERION_MISSING for criterion in criteria)
