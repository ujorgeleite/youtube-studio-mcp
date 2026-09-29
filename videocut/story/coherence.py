"""Coerência de cena depois do planejador: menos jump cuts, nada de áudio repetido.

Regras em `config/estilo.yaml`. Tudo aqui é determinístico e reaplicável sem modelo.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import load_yaml
from core.schema import SPEECH, Beat, Evidence, Inventory, Overlay, StoryVideo

EDGE_ROLES = ("gancho", "conclusao")
ROLE_WEIGHT = {"gancho": 5, "conclusao": 4, "mensagem": 3, "contexto": 2, "desenvolvimento": 1, "apoio": 0}


@dataclass
class SceneRules:
    merge_gap_s: float = 2.0
    max_block_s: float = 75.0
    min_block_s: float = 2.5
    min_words: int = 3
    unique_edge_roles: bool = True

    @classmethod
    def load(cls) -> "SceneRules":
        values = load_yaml("estilo.yaml").get("cenas", {})
        return cls(
            merge_gap_s=float(values.get("juntar_mesmo_take_s", cls.merge_gap_s)),
            max_block_s=float(values.get("bloco_maximo_s", cls.max_block_s)),
            min_block_s=float(values.get("bloco_minimo_s", cls.min_block_s)),
            min_words=int(values.get("palavras_minimas", cls.min_words)),
            unique_edge_roles=bool(values.get("papeis_unicos", cls.unique_edge_roles)),
        )


def _quote(inventory: Inventory, take_id: str, start_s: float, end_s: float) -> str:
    transcript = inventory.transcripts.get(take_id)
    return transcript.text_between(start_s, end_s)[:280] if transcript else ""


def merge(first: Beat, second: Beat, inventory: Inventory) -> Beat:
    """Um trecho contínuo do take: as imagens de apoio do segundo mudam de posição relativa."""
    shift = second.start_s - first.start_s
    overlays = [*first.overlays, *(Overlay(o.take_id, o.start_s, o.end_s, round(o.at_s + shift, 3)) for o in second.overlays)]
    observation = first.evidence[0].observation if first.evidence else ""
    role = max((first.role, second.role), key=lambda role: ROLE_WEIGHT.get(role, 1))
    end = max(first.end_s, second.end_s)
    evidence = [Evidence(first.take_id, first.start_s, end, _quote(inventory, first.take_id, first.start_s, end), observation)]
    return Beat(first.id, first.title, role, first.take_id, first.start_s, end, first.reason or second.reason,
                SPEECH if SPEECH in (first.audio, second.audio) else first.audio, overlays, evidence)


def word_count(beat: Beat) -> int:
    return len(beat.evidence[0].quote.split()) if beat.evidence and beat.evidence[0].quote else 0


def tidy(video: StoryVideo, inventory: Inventory, rules: SceneRules | None = None) -> list[str]:
    """Ajusta o vídeo no lugar e devolve o que foi feito, para o relatório."""
    rules = rules or SceneRules.load()
    notes: list[str] = []
    beats: list[Beat] = []
    merged = trimmed = 0
    for beat in video.beats:
        previous = beats[-1] if beats else None
        if previous and previous.take_id == beat.take_id and beat.start_s < previous.end_s:
            beat.start_s = round(previous.end_s, 3)
            trimmed += 1
            if beat.end_s - beat.start_s <= 0.3:
                continue
        if (previous and previous.take_id == beat.take_id and 0 <= beat.start_s - previous.end_s <= rules.merge_gap_s
                and beat.end_s - previous.start_s <= rules.max_block_s):
            beats[-1] = merge(previous, beat, inventory)
            merged += 1
            continue
        beats.append(beat)
    kept = []
    dropped = 0
    for index, beat in enumerate(beats):
        edge = beat.role in EDGE_ROLES and index in (0, len(beats) - 1)
        too_short = beat.duration_s < rules.min_block_s
        too_few_words = beat.audio == SPEECH and word_count(beat) < rules.min_words
        if not edge and (too_short or too_few_words):
            dropped += 1
            continue
        kept.append(beat)
    if rules.unique_edge_roles:
        for index, beat in enumerate(kept):
            if beat.role == "gancho" and index != 0 or beat.role == "conclusao" and index != len(kept) - 1:
                beat.role = "desenvolvimento"
        if kept and kept[-1].role not in ("conclusao", "mensagem"):
            kept[-1].role = "conclusao"
    for beat in kept:
        observation = beat.evidence[0].observation if beat.evidence else ""
        beat.evidence = [Evidence(beat.take_id, beat.start_s, beat.end_s,
                                  _quote(inventory, beat.take_id, beat.start_s, beat.end_s), observation)]
    video.beats = kept
    if merged:
        notes.append(f"{merged} bloco(s) seguidos do mesmo take foram unidos para evitar cortes secos.")
    if trimmed:
        notes.append(f"{trimmed} sobreposição(ões) de áudio entre blocos do mesmo take foram removidas.")
    if dropped:
        notes.append(f"{dropped} fragmento(s) curtos demais ou sem fala útil saíram da sequência.")
    return notes
