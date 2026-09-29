"""Etapa 3: comparar propostas e conferir se o material sustenta cada uma."""

from __future__ import annotations

from nicegui import ui

from core.project import ReviewState
from core.schema import CRITERION_MISSING, CRITERION_OK, VERDICT_INSUFFICIENT, VERDICT_MULTIPLE, Proposal
from core.timefmt import clock, span

from . import theme
from .evidence import open_evidence
from .shell import Shell
from .state import MATERIAL, REVIEW

VERDICT_TEXT = {
    "um_video": "Há material para um vídeo",
    VERDICT_MULTIPLE: "Há histórias independentes",
    VERDICT_INSUFFICIENT: "Falta material para uma história completa",
}


def choose(shell: Shell, proposal: Proposal) -> None:
    project = shell.studio.project
    if project.chosen != proposal.id:
        project.chosen = proposal.id
    for video in proposal.videos:
        if video.id not in project.review:
            project.review[video.id] = ReviewState(order=[beat.id for beat in video.beats], active=video.beats[0].id)
    project.save()
    shell.studio.video_id = proposal.videos[0].id
    shell.go(REVIEW)


def render(shell: Shell) -> None:
    project = shell.studio.project
    theme.title("03 / Histórias", "Escolha o que vale contar",
                "Compare a força da história e os trechos que a sustentam antes de montar qualquer vídeo.")
    report = project.report if project else None
    if report is None:
        with theme.panel():
            ui.label("Ainda não há propostas. Analise o material primeiro.").classes("vc-muted")
            theme.button("← Material", lambda: shell.go(MATERIAL)).classes("mt-3")
        return
    total = sum(take.duration_s for take in project.selected_takes)
    with ui.row().classes("w-full items-center gap-3 mb-4"):
        theme.pill(f"{len(project.selected_takes)} takes · {clock(total)} raw")
        theme.pill(VERDICT_TEXT.get(report.verdict, report.verdict), "amber" if report.verdict == VERDICT_INSUFFICIENT else "teal")
        for topic in report.topics[:5]:
            theme.pill(topic)
    if report.summary:
        ui.label(report.summary).classes("vc-muted mb-2")
    if project.intention and report.intention_check:
        with theme.panel().classes("mb-4"):
            theme.eyebrow("Sua intenção")
            ui.label(f"“{project.intention}”").classes("vc-small mt-1")
            ui.label(report.intention_check).classes("vc-muted vc-small")
    if report.verdict == VERDICT_INSUFFICIENT:
        insufficient_banner(report.proposals)
    with theme.layout():
        with theme.stack():
            if not report.proposals:
                with theme.panel("amber"):
                    ui.label("Nenhuma proposta passou pela validação.").classes("vc-h3")
                    ui.label("O material analisado não sustenta uma história com evidências.").classes("vc-muted")
            for proposal in report.proposals:
                proposal_card(shell, proposal)
        with theme.stack():
            focus = next((p for p in report.proposals if p.id == project.chosen), None) or next((p for p in report.proposals if p.recommended), None)
            if focus:
                criteria_panel(shell, focus)
            with theme.panel("amber"):
                ui.label("Seu critério vem primeiro").classes("vc-h3")
                ui.label("Mais vídeos não significa melhor aproveitamento. Cada proposta precisa funcionar por conta própria.").classes("vc-muted vc-small")
            if report.rejected:
                with ui.expansion(f"O validador descartou {len(report.rejected)} item(ns)").classes("w-full vc-small"):
                    for item in report.rejected:
                        ui.label(item).classes("vc-tiny vc-muted")
            theme.note("Cada afirmação aponta para arquivo e timestamp. Abra uma evidência para assistir ao trecho original.")


def insufficient_banner(proposals: list[Proposal]) -> None:
    gaps = [gap for proposal in proposals for gap in proposal.gaps]
    with theme.panel("amber").classes("mb-4"):
        theme.pill("Lacuna editorial", "amber")
        ui.label("Ainda não há uma história completa").classes("vc-h2 mt-2")
        for gap in gaps[:3]:
            ui.label(gap.description)
            if gap.suggestion:
                ui.label(f"Sugestão de gravação: {gap.suggestion}").classes("vc-small vc-muted")
        ui.label("Você ainda pode revisar um rascunho parcial, claramente identificado.").classes("vc-small vc-muted mt-1")


def _message_beat(proposal: Proposal):
    beats = [beat for video in proposal.videos for beat in video.beats]
    return next((beat for beat in beats if beat.role == "mensagem"), None) or next((beat for beat in beats if beat.evidence and beat.evidence[0].quote), None)


def proposal_card(shell: Shell, proposal: Proposal) -> None:
    letter = "Um vídeo principal" if not proposal.multiple else f"{len(proposal.videos)} vídeos independentes"
    with theme.panel("accent" if proposal.recommended else ""):
        with ui.row().classes("w-full items-center"):
            theme.eyebrow(f"{proposal.id} / {letter}")
            ui.space()
            if proposal.partial:
                theme.pill("Rascunho parcial", "amber")
            elif proposal.recommended:
                theme.pill("Recomendado", "teal")
        ui.label(proposal.title).classes("vc-h2 mt-3").style("font-size:24px" if proposal.recommended else "")
        if proposal.summary:
            ui.label(proposal.summary).classes("vc-muted")
        with ui.element("div").classes("vc-metrics"):
            theme.metric(clock(sum(video.duration_s for video in proposal.videos)), "montagem proposta")
            theme.metric(str(sum(len(video.beats) for video in proposal.videos)), "blocos narrativos")
            theme.metric(str(proposal.review_points), "pontos para revisar")
        if proposal.multiple:
            with ui.row().classes("gap-6 mb-2"):
                for number, video in enumerate(proposal.videos, start=1):
                    with ui.column().classes("gap-0"):
                        ui.label(f"{number:02d} · {video.title}").classes("vc-small").style("font-weight:650")
                        ui.label(f"{clock(video.duration_s)} · {len(video.beats)} blocos").classes("vc-tiny vc-muted")
        else:
            with ui.element("div").classes("vc-flow"):
                for index, beat in enumerate(proposal.videos[0].beats):
                    if index:
                        ui.label("→")
                    ui.label(beat.title).classes("step")
        beat = _message_beat(proposal)
        if beat and beat.evidence:
            evidence = beat.evidence[0]
            with ui.column().classes("w-full gap-0 mt-4").style("border-top:1px solid var(--line);padding-top:14px"):
                ui.label("Por que essa mensagem?").classes("vc-pill")
                with ui.element("div").classes("vc-evidence"):
                    ui.label(evidence.take_id).classes("vc-filetag")
                    with ui.column().classes("gap-0 flex-grow"):
                        ui.label(f"“{evidence.quote[:160]}”" if evidence.quote else evidence.observation).classes("vc-small")
                        ui.label(f"{span(evidence.start_s, evidence.end_s)} · {beat.title}").classes("vc-tiny vc-muted")
                    theme.button("Ver ↗", lambda _, e=evidence, b=beat: open_evidence(shell, e, b.reason), small=True)
        for gap in proposal.gaps:
            ui.label(f"◷ {gap.description}" + (f" — {gap.suggestion}" if gap.suggestion else "")).classes("vc-small warn mt-2")
        for warning in proposal.warnings[:4]:
            ui.label(warning).classes("vc-tiny warn")
        with ui.row().classes("mt-4 gap-3"):
            theme.button("Revisar esta proposta →" if not proposal.multiple else "Explorar divisão →",
                         lambda _, p=proposal: choose(shell, p), primary=proposal.recommended)
            opener = next((b for video in proposal.videos for b in video.beats if b.role == "gancho" and b.evidence), None)
            if opener:
                theme.button("Ver gancho sugerido", lambda _, b=opener: open_evidence(shell, b.evidence[0], b.reason))


def criteria_panel(shell: Shell, proposal: Proposal) -> None:
    with theme.panel():
        ui.label("O material sustenta a ideia?").classes("vc-h3")
        ui.label(f"Proposta {proposal.id}").classes("vc-tiny vc-muted")
        for criterion in proposal.criteria:
            ok = criterion.status == CRITERION_OK
            symbol, tone = ("✓", "check") if ok else ("✗", "bad") if criterion.status == CRITERION_MISSING else ("◷", "warn")
            with ui.element("div").classes("vc-check-row"):
                ui.label(symbol).classes(tone).style("font-size:16px")
                with ui.column().classes("gap-0 flex-grow"):
                    ui.label(criterion.label).classes("vc-small").style("font-weight:650")
                    ui.label(criterion.detail or ("Presente" if ok else criterion.status)).classes("vc-tiny vc-muted")
                    with ui.row().classes("gap-1 mt-1"):
                        for evidence in criterion.evidence[:3]:
                            ui.button(evidence.take_id, on_click=lambda _, e=evidence, c=criterion: open_evidence(shell, e, c.detail, c.label),
                                      color=None).props("flat dense no-caps").classes("vc-filetag")
