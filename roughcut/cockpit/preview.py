"""Operações puras sobre a cut-list para a prévia/edição — sem UI, sem ffmpeg.

Reordenar/remover beats, listar clipes que ficaram de fora e inserir um deles, e
achatar a cut-list em segmentos para o player tocar direto dos clipes de origem.
"""

from __future__ import annotations

from typing import Any


def used_clip_ids(cut_list: dict) -> set[str]:
    ids = set()
    for beat in cut_list.get("roughcut", []):
        for clip in beat.get("clips") or []:
            if clip.get("clip_id"):
                ids.add(clip["clip_id"])
    return ids


def leftover_clips(cut_list: dict, clip_map: dict[str, str]) -> list[str]:
    used = used_clip_ids(cut_list)
    return [clip_id for clip_id in clip_map if clip_id not in used]


def player_segments(cut_list: dict) -> list[dict[str, Any]]:
    """Segmentos tocáveis (só beats com clipes). B-roll slots não têm mídia."""
    segments = []
    for beat in cut_list.get("roughcut", []):
        for clip in beat.get("clips") or []:
            segments.append(
                {
                    "beat": beat.get("beat"),
                    "clip_id": clip["clip_id"],
                    "in": clip.get("in", "00:00:00"),
                    "out": clip.get("out", "00:00:00"),
                }
            )
    return segments


def move_beat(cut_list: dict, index: int, delta: int) -> None:
    beats = cut_list.get("roughcut", [])
    target = index + delta
    if 0 <= index < len(beats) and 0 <= target < len(beats):
        beats[index], beats[target] = beats[target], beats[index]


def remove_beat(cut_list: dict, index: int) -> None:
    beats = cut_list.get("roughcut", [])
    if 0 <= index < len(beats):
        beats.pop(index)


def insert_clip(
    cut_list: dict,
    clip_id: str,
    in_tc: str,
    out_tc: str,
    position: int | None = None,
    beat_name: str = "extra",
) -> None:
    beat = {
        "beat": beat_name,
        "clips": [{"clip_id": clip_id, "in": in_tc, "out": out_tc}],
        "broll_suggestion": "",
    }
    beats = cut_list.setdefault("roughcut", [])
    if position is None or position >= len(beats):
        beats.append(beat)
    else:
        beats.insert(max(0, position), beat)
