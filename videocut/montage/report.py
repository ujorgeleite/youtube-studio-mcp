"""Relatório editorial: explica escolhas e lacunas com as evidências de cada bloco."""

from __future__ import annotations

from pathlib import Path

from core.project import ReviewState
from core.schema import CRITERION_MISSING, CRITERION_OK, EditPlan, Inventory, Proposal, StoryVideo
from core.timefmt import clock, span

from .plan import ordered_beats

STATUS_MARK = {CRITERION_OK: "✓", CRITERION_MISSING: "✗"}


def _take_name(inventory: Inventory, take_id: str) -> str:
    take = inventory.take(take_id)
    return f"{take_id} ({take.name})" if take else take_id


def editorial_report(proposal: Proposal, video: StoryVideo, plan: EditPlan, inventory: Inventory, review: ReviewState | None) -> str:
    beats = ordered_beats(video, review)
    kept = {beat.id for beat in beats}
    lines = [
        f"# {video.title}",
        "",
        f"Proposta {proposal.id} · {proposal.title}" + (" · rascunho parcial" if proposal.partial else ""),
        "",
        f"**Mensagem:** {video.message or 'não definida'}",
        f"**Duração montada:** {clock(plan.duration_s)} · {len(beats)} blocos · {len(plan.broll_track)} imagens de apoio",
        f"**Formato:** {plan.format.width}×{plan.format.height} a {plan.format.fps:g} fps",
        "",
        "## Sequência",
        "",
    ]
    for number, beat in enumerate(beats, start=1):
        lines.append(f"### {number:02d} · {beat.title} ({beat.role})")
        lines.append(f"- Origem: {_take_name(inventory, beat.take_id)} · {span(beat.start_s, beat.end_s)} · áudio: {beat.audio}")
        if beat.reason:
            lines.append(f"- Motivo: {beat.reason}")
        for evidence in beat.evidence:
            if evidence.quote:
                lines.append(f"- Fala: “{evidence.quote}”")
            if evidence.observation:
                lines.append(f"- Imagem observada: {evidence.observation}")
        for overlay in beat.overlays:
            lines.append(f"- Apoio: {_take_name(inventory, overlay.take_id)} · {span(overlay.start_s, overlay.end_s)} sobre a fala a partir de {overlay.at_s:.1f}s")
        lines.append("")
    lines += ["## O material sustenta a ideia?", ""]
    for criterion in proposal.criteria:
        detail = f" — {criterion.detail}" if criterion.detail else ""
        lines.append(f"- {STATUS_MARK.get(criterion.status, '◷')} **{criterion.label}**: {criterion.status}{detail}")
    if proposal.gaps:
        lines += ["", "## Lacunas", ""]
        lines += [f"- {gap.description}" + (f" · Sugestão: {gap.suggestion}" if gap.suggestion else "") for gap in proposal.gaps]
    if proposal.warnings:
        lines += ["", "## Avisos", ""]
        lines += [f"- {warning}" for warning in proposal.warnings]
    removed = [beat for beat in video.beats if beat.id not in kept]
    if removed:
        lines += ["", "## Excluídos na revisão", ""]
        lines += [f"- {beat.title} · {_take_name(inventory, beat.take_id)} · {span(beat.start_s, beat.end_s)}" for beat in removed]
    lines += ["", "Originais preservados. Timestamps referem-se aos arquivos brutos.", ""]
    return "\n".join(lines)


def write_report(text: str, destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
