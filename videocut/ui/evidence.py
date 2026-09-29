"""Janela de evidência: o trecho original tocando, o fato observado e a interpretação."""

from __future__ import annotations

from nicegui import ui

from core.schema import Beat, Evidence
from core.timefmt import span

from . import theme
from .preview import play, player
from .shell import Shell


async def open_evidence(shell: Shell, evidence: Evidence, interpretation: str = "", heading: str = "Por que este trecho entra?") -> None:
    project = shell.studio.project
    take = project.take(evidence.take_id)
    with shell.root, ui.dialog() as dialog, theme.panel().style("width:min(770px,calc(100vw - 35px));max-height:90vh;overflow:auto"):
        with ui.row().classes("w-full items-center"):
            theme.eyebrow(f"Evidência / {evidence.take_id}")
            ui.space()
            theme.button("×", dialog.close, small=True)
        ui.label(heading).classes("vc-h2")
        ui.label(f"{take.name if take else evidence.take_id} · {span(evidence.start_s, evidence.end_s)}").classes("vc-muted vc-small")
        player("vc-ev", "260px")
        theme.pill("Fato observado", "teal").classes("mt-4")
        if evidence.quote:
            ui.label(f"“{evidence.quote}”").style("font-size:19px").classes("mt-2")
        else:
            ui.label("Sem fala neste trecho.").classes("vc-muted mt-2")
        if evidence.observation:
            ui.label(f"Imagem: {evidence.observation}").classes("vc-small vc-muted")
        if interpretation:
            with ui.column().classes("w-full gap-1 mt-4").style("border-top:1px solid var(--line);padding-top:14px"):
                ui.label("Interpretação editorial").classes("vc-h3")
                ui.label(interpretation).classes("vc-muted")
        theme.note("A fala vem da transcrição e a imagem da análise visual deste trecho; nada aqui foi escrito pelo planejador.")
    dialog.open()
    if take and not shell.working:
        clip = Beat("evidencia", "", "", evidence.take_id, evidence.start_s, evidence.end_s)
        with shell.activity(f"Abrindo evidência de {take.id}") as step, shell.root:
            await play([clip], {take.id: take}, project.layout, "vc-ev", step)
