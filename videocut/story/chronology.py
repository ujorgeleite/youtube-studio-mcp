"""Montagem base: o dia na ordem em que aconteceu, sem depender do modelo.

É o primeiro corte que um editor faria num vlog: todas as falas aproveitáveis
em ordem cronológica, sem repetições nem trechos com problema técnico, com os
momentos de ação disponíveis como imagem de apoio ou blocos próprios. O modelo depois organiza
capítulos e escolhe o que fica; se ele falhar, esta base continua valendo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from core.schema import ACTION, BROLL, PROBLEM, SPEECH, Inventory, Moment, Take

from .validate import normalize_text

CAMERA_TIMESTAMP = re.compile(r"(20\d{2})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})")
MIN_SPEECH_S = 1.2
MIN_SPEECH_WORDS = 3
MIN_DISTINCT_RATIO = 0.5
RETAKE_SIMILARITY = 0.72
AMBIENT_MAX_S = 8.0


def recorded_at(take: Take) -> datetime | None:
    """Câmeras como a DJI gravam data e hora no nome: DJI_20260927133533_0073_D.MP4."""
    match = CAMERA_TIMESTAMP.search(take.name)
    if not match:
        return None
    try:
        return datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def chronological(takes: list[Take]) -> list[Take]:
    return sorted(takes, key=lambda take: (recorded_at(take) or datetime.max, take.name.lower()))


def repetitive(text: str) -> bool:
    """Música de fundo vira “Música Música Música” na transcrição: poucas palavras distintas."""
    words = normalize_text(text).split()
    return len(words) >= MIN_SPEECH_WORDS and len(set(words)) / len(words) < MIN_DISTINCT_RATIO


def usable_speech(moment: Moment) -> bool:
    return (moment.kind == SPEECH and moment.duration_s >= MIN_SPEECH_S
            and len(moment.speech.split()) >= MIN_SPEECH_WORDS and PROBLEM not in moment.issues
            and not repetitive(moment.speech))


def is_retake(earlier: Moment, later: Moment) -> bool:
    """Falas quase iguais em sequência: a pessoa repetiu; vale a última tentativa."""
    first, second = normalize_text(earlier.speech), normalize_text(later.speech)
    return bool(first and second) and SequenceMatcher(None, first, second).ratio() >= RETAKE_SIMILARITY


@dataclass
class BaseCut:
    speech: list[Moment] = field(default_factory=list)
    broll: list[Moment] = field(default_factory=list)
    retakes: list[Moment] = field(default_factory=list)
    order: dict[str, int] = field(default_factory=dict)

    @property
    def speech_s(self) -> float:
        return sum(moment.duration_s for moment in self.speech)


def base_cut(inventory: Inventory) -> BaseCut:
    takes = chronological(inventory.takes)
    order = {take.id: index for index, take in enumerate(takes)}
    moments = sorted(inventory.moments, key=lambda moment: (order.get(moment.take_id, len(order)), moment.start_s))
    cut = BaseCut(order=order)
    for moment in moments:
        if moment.take_id not in order:
            continue
        if usable_speech(moment):
            if cut.speech and is_retake(cut.speech[-1], moment):
                cut.retakes.append(cut.speech.pop())
            cut.speech.append(moment)
        elif moment.kind in (ACTION, BROLL) and PROBLEM not in moment.issues and moment.duration_s >= 2:
            cut.broll.append(moment)
    return cut


def moment_block(moment: Moment, role: str = "desenvolvimento", title: str = "", reason: str = "") -> dict:
    """Bloco no formato do planejador; o validador cuida de frases inteiras e evidências."""
    block = {"momento": moment.id, "papel": role, "titulo": title or short_title(moment), "motivo": reason}
    if moment.kind != SPEECH and moment.duration_s > AMBIENT_MAX_S:
        block["inicio"] = moment.start_s
        block["fim"] = moment.start_s + AMBIENT_MAX_S
    return block


def short_title(moment: Moment) -> str:
    words = (moment.speech or moment.visual).split()
    return " ".join(words[:6]).strip(".,;:") or moment.id
