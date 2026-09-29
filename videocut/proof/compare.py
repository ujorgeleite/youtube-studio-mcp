"""Compara a proposta com uma edição já feita à mão do mesmo material.

A edição final é transcrita e cada frase dela é alinhada às frases dos takes
brutos. Assim sabemos quais falas a pessoa usou e em que ordem, sem depender de
timeline exportada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from core.project import ReviewState
from core.schema import Inventory, Sentence, StoryVideo, Transcript
from core.timefmt import clock, span
from montage.plan import ordered_beats
from story.validate import normalize_text

MATCH_THRESHOLD = 0.62

RawKey = tuple[str, int]


@dataclass
class Alignment:
    used: list[RawKey] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


@dataclass
class Comparison:
    used: list[RawKey]
    proposed: list[RawKey]
    unmatched: list[str]
    edit_duration_s: float
    proposal_duration_s: float

    @property
    def common(self) -> list[RawKey]:
        proposed = set(self.proposed)
        return [key for key in self.used if key in proposed]

    @property
    def recall(self) -> float:
        return len(self.common) / len(set(self.used)) if self.used else 0.0

    @property
    def precision(self) -> float:
        return len(set(self.common)) / len(set(self.proposed)) if self.proposed else 0.0

    @property
    def order_agreement(self) -> float:
        """Fração de pares de falas em comum que aparecem na mesma ordem (Kendall normalizado)."""
        position = {key: index for index, key in enumerate(dict.fromkeys(self.proposed))}
        keys = list(dict.fromkeys(self.common))
        pairs = [(a, b) for index, a in enumerate(keys) for b in keys[index + 1:]]
        if not pairs:
            return 1.0 if keys else 0.0
        return sum(position[a] < position[b] for a, b in pairs) / len(pairs)


def similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, normalize_text(first), normalize_text(second)).ratio()


def raw_sentences(inventory: Inventory) -> dict[RawKey, Sentence]:
    return {(take_id, index): sentence for take_id, transcript in inventory.transcripts.items()
            for index, sentence in enumerate(transcript.sentences)}


def align(edit: Transcript, inventory: Inventory, threshold: float = MATCH_THRESHOLD) -> Alignment:
    candidates = raw_sentences(inventory)
    result = Alignment()
    for sentence in edit.sentences:
        best = max(candidates, key=lambda key: similarity(sentence.text, candidates[key].text), default=None)
        if best is not None and similarity(sentence.text, candidates[best].text) >= threshold:
            result.used.append(best)
        else:
            result.unmatched.append(sentence.text)
    return result


def proposed_sentences(video: StoryVideo, review: ReviewState | None, inventory: Inventory) -> list[RawKey]:
    keys = []
    candidates = raw_sentences(inventory)
    for beat in ordered_beats(video, review):
        for key, sentence in candidates.items():
            if key[0] == beat.take_id and sentence.start_s >= beat.start_s - 0.3 and sentence.end_s <= beat.end_s + 0.3:
                keys.append(key)
    return keys


def compare(edit: Transcript, edit_duration_s: float, video: StoryVideo, review: ReviewState | None, inventory: Inventory) -> Comparison:
    alignment = align(edit, inventory)
    return Comparison(
        used=alignment.used,
        proposed=proposed_sentences(video, review, inventory),
        unmatched=alignment.unmatched,
        edit_duration_s=edit_duration_s,
        proposal_duration_s=sum(beat.duration_s for beat in ordered_beats(video, review)),
    )


def comparison_report(result: Comparison, inventory: Inventory, edit_name: str, video: StoryVideo) -> str:
    sentences = raw_sentences(inventory)
    used, proposed = set(result.used), set(result.proposed)

    def line(key: RawKey) -> str:
        sentence = sentences[key]
        return f"- {key[0]} {span(sentence.start_s, sentence.end_s)} · “{sentence.text}”"

    lines = [
        f"# Proposta × edição real · {video.title}",
        "",
        f"Edição de referência: `{edit_name}`",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Falas da sua edição encontradas na proposta (recall) | {result.recall:.0%} |",
        f"| Falas da proposta que você também usou (precisão) | {result.precision:.0%} |",
        f"| Concordância de ordem entre falas em comum | {result.order_agreement:.0%} |",
        f"| Duração da sua edição | {clock(result.edit_duration_s)} |",
        f"| Duração da proposta | {clock(result.proposal_duration_s)} |",
        f"| Frases da edição sem correspondência nos takes | {len(result.unmatched)} |",
        "",
        "## Você usou e a proposta também", "",
        *[line(key) for key in dict.fromkeys(result.common)],
        "", "## Você usou e a proposta deixou de fora", "",
        *[line(key) for key in dict.fromkeys(result.used) if key not in proposed],
        "", "## A proposta usou e você não", "",
        *[line(key) for key in dict.fromkeys(result.proposed) if key not in used],
    ]
    if result.unmatched:
        lines += ["", "## Frases da edição sem correspondência", "",
                  "Narração gravada depois, música com letra ou takes fora da análise.", ""]
        lines += [f"- “{text}”" for text in result.unmatched]
    lines += ["", "Métricas cobrem fala. Escolhas de imagem, ritmo e humor precisam do seu olhar.", ""]
    return "\n".join(lines)


def write_comparison(text: str, destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
