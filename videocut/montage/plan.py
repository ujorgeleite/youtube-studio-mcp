"""Transforma a proposta revisada em um plano executável com faixas independentes."""

from __future__ import annotations

from collections import Counter

from core.project import ReviewState
from core.schema import SPEECH, AudioClip, Beat, EditPlan, OutputFormat, Take, StoryVideo, VideoClip

STANDARD_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
AMBIENT_UNDER_BROLL_DB = -22.0


def ordered_beats(video: StoryVideo, review: ReviewState | None) -> list[Beat]:
    """Aplica a ordem e as exclusões da revisão; blocos novos entram no fim."""
    if review is None:
        return list(video.beats)
    by_id = {beat.id: beat for beat in video.beats}
    order = [beat_id for beat_id in review.order if beat_id in by_id]
    order += [beat.id for beat in video.beats if beat.id not in order]
    skip = set(review.excluded)
    return [by_id[beat_id] for beat_id in order if beat_id not in skip]


def _nearest_fps(value: float) -> float:
    return min(STANDARD_FPS, key=lambda standard: abs(standard - value)) if value > 0 else 30.0


def choose_format(takes: list[Take], beats: list[Beat]) -> OutputFormat:
    """Orientação e FPS seguem a maioria do tempo em tela; resolução é Full HD."""
    by_id = {take.id: take for take in takes}
    orientation: Counter[str] = Counter()
    rates: Counter[float] = Counter()
    for beat in beats:
        take = by_id.get(beat.take_id)
        if take is None:
            continue
        orientation["vertical" if take.height > take.width else "horizontal"] += beat.duration_s
        rates[_nearest_fps(take.fps)] += beat.duration_s
    fps = rates.most_common(1)[0][0] if rates else 30.0
    if orientation and orientation.most_common(1)[0][0] == "vertical":
        return OutputFormat(width=1080, height=1920, fps=fps)
    return OutputFormat(width=1920, height=1080, fps=fps)


def build_edit_plan(
    proposal_id: str,
    video: StoryVideo,
    takes: list[Take],
    review: ReviewState | None = None,
    output: OutputFormat | None = None,
) -> EditPlan:
    beats = ordered_beats(video, review)
    by_id = {take.id: take for take in takes}
    plan = EditPlan(proposal_id, video.id, video.title, format=output or choose_format(takes, beats))
    fade = plan.format.audio_fade_s
    cursor = 0.0
    for beat in beats:
        take = by_id.get(beat.take_id)
        if take is None:
            continue
        plan.sources[take.id] = take.path
        plan.video.append(VideoClip(take.id, beat.start_s, beat.end_s, round(cursor, 3), beat.id))
        if take.has_audio:
            plan.audio.append(AudioClip(take.id, beat.start_s, beat.end_s, round(cursor, 3), beat.id,
                                        role=beat.audio, fade_in_s=fade, fade_out_s=fade))
        for overlay in beat.overlays:
            source = by_id.get(overlay.take_id)
            if source is None:
                continue
            plan.sources[source.id] = source.path
            start = round(cursor + overlay.at_s, 3)
            plan.video.append(VideoClip(source.id, overlay.start_s, overlay.end_s, start, beat.id, broll=True))
            if source.has_audio and beat.audio == SPEECH:
                plan.audio.append(AudioClip(source.id, overlay.start_s, overlay.end_s, start, beat.id, role="ambiente",
                                            gain_db=AMBIENT_UNDER_BROLL_DB, fade_in_s=0.4, fade_out_s=0.4))
        cursor += beat.duration_s
    return plan
