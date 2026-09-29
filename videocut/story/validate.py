"""Converte a resposta do planejador em propostas ancoradas no inventário.

Nada do que o modelo escreve chega à pessoa como fato: ids inexistentes são
descartados, tempos ficam dentro do momento citado, cortes de fala respeitam
frases inteiras e as evidências exibidas vêm da transcrição e da observação.
"""

from __future__ import annotations

import re
import unicodedata

from core.schema import (
    BEAT_ROLES, CRITERIA, CRITERION_MISSING, CRITERION_OK, CRITERION_REVIEW, PROBLEM, SPEECH,
    VERDICT_INSUFFICIENT, VERDICT_MULTIPLE, VERDICT_SINGLE, Beat, Criterion, Evidence, Gap, Inventory, Moment,
    Overlay, Proposal, StoryReport, StoryVideo,
)
from core.timefmt import clock, parse_clock

from .criteria import assess, is_partial

SPEECH_PAD_BEFORE_S = 0.12
SPEECH_PAD_AFTER_S = 0.25
MIN_BEAT_S = 0.8
MIN_OVERLAY_S = 1.5
QUOTE_LIMIT = 280
VERDICTS = {VERDICT_SINGLE, VERDICT_MULTIPLE, VERDICT_INSUFFICIENT}
STATUSES = {CRITERION_OK, CRITERION_REVIEW, CRITERION_MISSING}
ROLE_ALIASES = {"conclusão": "conclusao", "encerramento": "conclusao", "abertura": "gancho", "hook": "gancho"}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def quote_supported(quote: str, spoken: str) -> bool:
    wanted, available = normalize_text(quote), normalize_text(spoken)
    if not wanted:
        return True
    if wanted in available:
        return True
    words = wanted.split()
    present = set(available.split())
    return len(words) >= 4 and sum(word in present for word in words) / len(words) >= 0.85


def _seconds(value: object, fallback: float) -> float:
    if value in (None, ""):
        return fallback
    try:
        return parse_clock(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _status(value: object) -> str:
    text = normalize_text(str(value or ""))
    return text if text in STATUSES else CRITERION_REVIEW


def _role(value: object) -> str:
    text = str(value or "").strip().lower()
    text = ROLE_ALIASES.get(text, text)
    return text if text in BEAT_ROLES else "desenvolvimento"


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


class ReportBuilder:
    def __init__(self, inventory: Inventory, target_s: float | None = None):
        self.inventory = inventory
        self.target_s = target_s
        self.moments = {moment.id: moment for moment in inventory.moments}
        self.rejected: list[str] = []

    def take_duration(self, take_id: str) -> float:
        take = self.inventory.take(take_id)
        return take.duration_s if take else float("inf")

    def spoken(self, take_id: str, start_s: float, end_s: float) -> str:
        transcript = self.inventory.transcripts.get(take_id)
        return transcript.text_between(start_s, end_s) if transcript else ""

    def evidence_for(self, moment: Moment, start_s: float | None = None, end_s: float | None = None) -> Evidence:
        start = moment.start_s if start_s is None else start_s
        end = moment.end_s if end_s is None else end_s
        quote = self.spoken(moment.take_id, start, end) or moment.speech
        return Evidence(moment.take_id, round(start, 3), round(end, 3), quote[:QUOTE_LIMIT], moment.visual)

    def bounds(self, raw: dict, moment: Moment) -> tuple[float, float]:
        start = min(max(_seconds(raw.get("inicio"), moment.start_s), moment.start_s), moment.end_s)
        end = min(max(_seconds(raw.get("fim"), moment.end_s), moment.start_s), moment.end_s)
        if end - start < MIN_BEAT_S:
            return moment.start_s, moment.end_s
        return start, end

    def snap_to_sentences(self, take_id: str, start_s: float, end_s: float) -> tuple[float, float]:
        """Expande o corte até frases inteiras e dá um respiro antes e depois."""
        transcript = self.inventory.transcripts.get(take_id)
        if transcript and transcript.sentences:
            touching = [s for s in transcript.sentences if min(end_s, s.end_s) - max(start_s, s.start_s) > 0]
            if touching:
                start_s = min(start_s, touching[0].start_s)
                end_s = max(end_s, touching[-1].end_s)
        return max(0.0, start_s - SPEECH_PAD_BEFORE_S), min(self.take_duration(take_id), end_s + SPEECH_PAD_AFTER_S)

    def overlays(self, items: list, beat: Beat, label: str, warnings: list[str]) -> list[Overlay]:
        result: list[Overlay] = []
        cursor = min(1.0, beat.duration_s * 0.15)
        for raw in items:
            if not isinstance(raw, dict):
                continue
            moment = self.moments.get(str(raw.get("momento", "")))
            if moment is None:
                self.rejected.append(f"{label}: imagem de apoio cita o momento inexistente “{raw.get('momento')}”.")
                continue
            if moment.kind == PROBLEM:
                warnings.append(f"{label}: imagem de apoio {moment.id} tem problema técnico ({', '.join(moment.issues)}) e foi ignorada.")
                continue
            if moment.take_id == beat.take_id and min(beat.end_s, moment.end_s) - max(beat.start_s, moment.start_s) > 0:
                continue
            start, end = self.bounds(raw, moment)
            room = beat.duration_s - cursor - 0.3
            length = min(end - start, room)
            if length < MIN_OVERLAY_S:
                break
            result.append(Overlay(moment.take_id, round(start, 3), round(start + length, 3), round(cursor, 3)))
            cursor += length
        return result

    def beat(self, raw: dict, beat_id: str, warnings: list[str]) -> Beat | None:
        title = str(raw.get("titulo") or "Bloco").strip()
        moment = self.moments.get(str(raw.get("momento", "")).strip())
        if moment is None:
            self.rejected.append(f"Bloco “{title}” cita o momento inexistente “{raw.get('momento')}” e foi descartado.")
            return None
        start, end = self.bounds(raw, moment)
        audio = SPEECH if moment.speech else "ambiente"
        if audio == SPEECH:
            start, end = self.snap_to_sentences(moment.take_id, start, end)
        if moment.kind == PROBLEM:
            warnings.append(f"“{title}” usa {moment.id}, que tem problema técnico ({', '.join(moment.issues)}).")
        quote = str(raw.get("citacao") or "").strip()
        if quote and not quote_supported(quote, self.spoken(moment.take_id, start, end) or moment.speech):
            warnings.append(f"“{title}”: a citação sugerida não aparece na fala de {moment.id}; mostrando a transcrição real.")
        beat = Beat(
            id=beat_id, title=title, role=_role(raw.get("papel")), take_id=moment.take_id,
            start_s=round(start, 3), end_s=round(end, 3), reason=str(raw.get("motivo") or "").strip(), audio=audio,
            evidence=[self.evidence_for(moment, start, end)],
        )
        beat.overlays = self.overlays(_list(raw.get("apoio")), beat, title, warnings)
        return beat

    def video(self, raw: dict, video_id: str, warnings: list[str]) -> StoryVideo | None:
        title = str(raw.get("titulo") or "Vídeo").strip()
        beats = []
        for number, item in enumerate(_list(raw.get("blocos")), start=1):
            if isinstance(item, dict) and (beat := self.beat(item, f"{video_id}.b{number:02d}", warnings)):
                beats.append(beat)
        used: dict[tuple[str, float, float], str] = {}
        for beat in beats:
            key = (beat.take_id, round(beat.start_s), round(beat.end_s))
            if key in used:
                warnings.append(f"“{beat.title}” repete o trecho de “{used[key]}”.")
            used[key] = beat.title
        if not beats:
            self.rejected.append(f"Vídeo “{title}” ficou sem blocos válidos e foi descartado.")
            return None
        video = StoryVideo(video_id, title, str(raw.get("mensagem") or "").strip(), beats)
        if self.target_s and video.duration_s > self.target_s * 1.25:
            warnings.append(f"“{title}” tem {clock(video.duration_s)}, acima da duração desejada ({clock(self.target_s)}).")
        return video

    def suggested_criteria(self, raw: object) -> dict[str, Criterion]:
        result = {}
        for key, value in (raw.items() if isinstance(raw, dict) else []):
            if key not in CRITERIA or not isinstance(value, dict):
                continue
            evidence = [self.evidence_for(self.moments[item]) for item in _list(value.get("momentos")) if item in self.moments]
            result[key] = Criterion(key, _status(value.get("status")), str(value.get("detalhe") or "").strip(), evidence)
        return result

    @staticmethod
    def gaps(raw: dict) -> list[Gap]:
        return [Gap(str(gap.get("descricao") or "").strip(), str(gap.get("sugestao") or "").strip())
                for gap in _list(raw.get("lacunas")) if isinstance(gap, dict) and gap.get("descricao")]

    def proposal(self, raw: dict, proposal_id: str) -> Proposal | None:
        warnings = [str(item) for item in _list(raw.get("avisos")) if str(item).strip()]
        videos = []
        for number, item in enumerate(_list(raw.get("videos")), start=1):
            if isinstance(item, dict) and (video := self.video(item, f"{proposal_id.lower()}{number}", warnings)):
                videos.append(video)
        title = str(raw.get("titulo") or f"Proposta {proposal_id}").strip()
        if not videos:
            self.rejected.append(f"Proposta “{title}” não tinha vídeos válidos e foi descartada.")
            return None
        proposal = Proposal(
            id=proposal_id, title=title, summary=str(raw.get("resumo") or "").strip(),
            recommended=bool(raw.get("recomendada")), videos=videos, warnings=warnings, gaps=self.gaps(raw),
        )
        proposal.criteria = assess(proposal, self.suggested_criteria(raw.get("criterios")))
        proposal.partial = bool(raw.get("parcial")) or is_partial(proposal.criteria)
        return proposal


def _verdict(raw: object, proposals: list[Proposal]) -> str:
    if not proposals or all(proposal.partial for proposal in proposals):
        return VERDICT_INSUFFICIENT
    stated = normalize_text(str(raw or "")).replace(" ", "_")
    if stated in VERDICTS:
        return stated
    recommended = next((proposal for proposal in proposals if proposal.recommended), proposals[0])
    return VERDICT_MULTIPLE if recommended.multiple else VERDICT_SINGLE


def build_report(raw: dict, inventory: Inventory, target_s: float | None = None) -> StoryReport:
    builder = ReportBuilder(inventory, target_s)
    proposals: list[Proposal] = []
    gaps: list[Gap] = []
    for item in _list(raw.get("propostas")) if isinstance(raw, dict) else []:
        if isinstance(item, dict):
            proposal = builder.proposal(item, chr(ord("A") + len(proposals)))
            if proposal:
                proposals.append(proposal)
            else:
                gaps.extend(gap for gap in builder.gaps(item) if gap not in gaps)
    recommended = [proposal for proposal in proposals if proposal.recommended and not proposal.partial]
    for proposal in proposals:
        proposal.recommended = False
    if proposals:
        (recommended or [next((p for p in proposals if not p.partial), proposals[0])])[0].recommended = True
    data = raw if isinstance(raw, dict) else {}
    return StoryReport(
        verdict=_verdict(data.get("veredito"), proposals),
        summary=str(data.get("resumo") or "").strip(),
        topics=[str(topic).strip() for topic in _list(data.get("temas")) if str(topic).strip()],
        intention_check=str(data.get("intencao") or "").strip(),
        proposals=proposals,
        rejected=builder.rejected,
        gaps=gaps,
    )
