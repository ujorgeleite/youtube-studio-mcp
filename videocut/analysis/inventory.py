"""Inventário de momentos: une fala e imagem em trechos citáveis por id."""

from __future__ import annotations

from core.schema import ACTION, BROLL, PROBLEM, SPEECH, Inventory, Moment, Take, Transcript, VisualObservation

UNUSABLE = {"tela_preta", "obstruido", "escuro", "desfocado"}
SPEECH_JOIN_GAP_S = 1.5
SPEECH_MOMENT_MAX_S = 35.0
MIN_VISUAL_REMAINDER_S = 3.0


def _overlaps(start_s: float, end_s: float, other_start: float, other_end: float) -> bool:
    return min(end_s, other_end) - max(start_s, other_start) > 0


def _visual_summary(observations: list[VisualObservation], start_s: float, end_s: float) -> tuple[str, list[str], float]:
    inside = [item for item in observations if _overlaps(start_s, end_s, item.start_s, item.end_s)]
    parts = []
    for item in inside:
        text = item.action or item.description
        if text and text not in parts:
            parts.append(text)
    issues = sorted({issue for item in inside for issue in item.issues})
    interest = max((item.interest for item in inside), default=0.5)
    return "; ".join(parts), issues, interest


def speech_spans(transcript: Transcript | None) -> list[tuple[float, float, str]]:
    spans: list[tuple[float, float, str]] = []
    for sentence in transcript.sentences if transcript else []:
        if spans and sentence.start_s - spans[-1][1] <= SPEECH_JOIN_GAP_S and sentence.end_s - spans[-1][0] <= SPEECH_MOMENT_MAX_S:
            start, _, text = spans[-1]
            spans[-1] = (start, sentence.end_s, f"{text} {sentence.text}")
        else:
            spans.append((sentence.start_s, sentence.end_s, sentence.text))
    return spans


def uncovered(start_s: float, end_s: float, spans: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    """Partes de um intervalo sem fala, para aproveitar como ação ou imagem de apoio."""
    pieces = [(start_s, end_s)]
    for span_start, span_end, _ in spans:
        next_pieces = []
        for piece_start, piece_end in pieces:
            if span_end <= piece_start or span_start >= piece_end:
                next_pieces.append((piece_start, piece_end))
                continue
            if span_start > piece_start:
                next_pieces.append((piece_start, span_start))
            if span_end < piece_end:
                next_pieces.append((span_end, piece_end))
        pieces = next_pieces
    return [(round(a, 3), round(b, 3)) for a, b in pieces if b - a >= MIN_VISUAL_REMAINDER_S]


def build_moments(take: Take, transcript: Transcript | None, observations: list[VisualObservation]) -> list[Moment]:
    drafts: list[Moment] = []
    spans = speech_spans(transcript)
    for start, end, text in spans:
        visual, issues, interest = _visual_summary(observations, start, end)
        drafts.append(Moment("", take.id, round(start, 3), round(end, 3), SPEECH, text, visual, issues, interest))
    for item in observations:
        if UNUSABLE & set(item.issues):
            kind = PROBLEM
        elif item.action:
            kind = ACTION
        else:
            kind = BROLL
        for start, end in uncovered(item.start_s, item.end_s, spans):
            drafts.append(Moment("", take.id, start, end, kind, "", item.action or item.description, list(item.issues), item.interest))
    drafts.sort(key=lambda moment: moment.start_s)
    for number, moment in enumerate(drafts, start=1):
        moment.id = f"{take.id}.{number:02d}"
    return drafts


def build_inventory(
    takes: list[Take],
    transcripts: dict[str, Transcript],
    observations: dict[str, list[VisualObservation]],
    failed: dict[str, str] | None = None,
) -> Inventory:
    moments = []
    for take in takes:
        if failed and take.id in failed:
            continue
        moments.extend(build_moments(take, transcripts.get(take.id), observations.get(take.id, [])))
    return Inventory(
        takes=takes,
        transcripts=transcripts,
        observations=[item for take in takes for item in observations.get(take.id, [])],
        moments=moments,
        failed=dict(failed or {}),
    )
