"""Roda agentes em background com o cartão de atividade e o Mac acordado."""

from __future__ import annotations

from nicegui import run

from analysis.pipeline import Analysis, AnalysisMonitor
from core.keepawake import KEEP_AWAKE

from .analysis_view import MODEL_FACTORY
from .shell import Shell


async def run_selected_agents(shell: Shell, keys: list[str], video_id: str) -> None:
    studio = shell.studio
    if studio.busy or studio.project is None or shell.refuse_if_working():
        return
    monitor = AnalysisMonitor()
    analysis = Analysis(studio.project, monitor, MODEL_FACTORY)
    try:
        with shell.activity("Rodando agente" if len(keys) == 1 else f"Rodando {len(keys)} agentes") as step, KEEP_AWAKE:
            step("Carregando o modelo na memória…")
            outputs = await run.io_bound(analysis.run_agents, keys, video_id)
            step(f"{len(outputs)} resultado(s) salvo(s) em analise/agentes/", 1.0)
    except Exception as error:  # noqa: BLE001 - o cartão de atividade já mostra o erro
        shell.notify(f"O agente não terminou: {error}", "negative")
        return
    shell.notify("Agente concluído. O resultado está abaixo e em analise/agentes/.", "positive")
    shell.main.refresh()
