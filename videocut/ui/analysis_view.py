"""Etapa 2: análise em background com progresso por take e por etapa."""

from __future__ import annotations

from nicegui import run, ui

from analysis.pipeline import STAGES, Analysis, AnalysisCancelled, AnalysisMonitor
from analysis.vlm import MlxModel
from core.project import STAGE_FAILED, STAGE_READY
from core.timefmt import stopwatch

from . import theme
from .shell import Shell
from .state import ANALYSIS, MATERIAL, STORIES

MODEL_FACTORY = MlxModel
STAGE_LABELS = {"pendente": "Na fila", "midia": "Preparando", "fala": "Transcrevendo", "visao": "Descrevendo",
                STAGE_READY: "Pronto", STAGE_FAILED: "Falhou"}


async def start_analysis(shell: Shell) -> None:
    studio = shell.studio
    project = studio.project
    if studio.busy or project is None:
        return
    if not project.selected:
        shell.notify("Selecione pelo menos um take.", "warning")
        return
    studio.monitor = AnalysisMonitor()
    studio.analyzing = True
    studio.inventory_cache = None
    shell.go(ANALYSIS)
    try:
        await run.io_bound(Analysis(project, studio.monitor, MODEL_FACTORY).run)
    except AnalysisCancelled:
        shell.notify("Análise cancelada. O que já foi transcrito e descrito ficou em cache.")
    except Exception as error:  # noqa: BLE001 - a mensagem aparece na tela; o lote já tratou falhas por take
        shell.notify(f"A análise não terminou: {error}", "negative")
    else:
        shell.notify("Análise concluída.", "positive")
    finally:
        studio.analyzing = False
    shell.go(STORIES if project.report and not studio.monitor.error and not studio.monitor.cancel.is_set() else ANALYSIS)


def render(shell: Shell) -> None:
    studio = shell.studio
    theme.title("02 / Análise", "Entendendo o material",
                "A análise aparece por take enquanto o sistema procura conexões entre imagem e fala.")
    if studio.project is None or (studio.monitor is None and not studio.project.status):
        with theme.panel():
            ui.label("Nenhuma análise em andamento.").classes("vc-muted")
            theme.button("← Escolher material", lambda: shell.go(MATERIAL)).classes("mt-3")
        return

    @ui.refreshable
    def live() -> None:
        live_content(shell)

    live()
    shell.on_live(lambda: live.refresh() if studio.analyzing else None)


def live_content(shell: Shell) -> None:
    studio = shell.studio
    project = studio.project
    monitor = studio.monitor or AnalysisMonitor()
    takes = project.selected_takes
    finished = [take for take in takes if project.status.get(take.id) and project.status[take.id].stage in (STAGE_READY, STAGE_FAILED)]
    fractions = [project.status[take.id].fraction if take.id in project.status else 0.0 for take in takes]
    overall = (sum(fractions) / len(fractions) * 0.9 if fractions else 0) + (0.1 if project.report and not studio.analyzing else 0)
    with theme.layout():
        with theme.stack():
            with theme.panel():
                theme.eyebrow("Análise local · " + ("em andamento" if studio.analyzing else "encerrada"))
                with ui.row().classes("items-baseline gap-4"):
                    ui.label(f"{len(finished)} / {len(takes)}").classes("vc-clock")
                    ui.label("takes").classes("vc-h2")
                    ui.space()
                    ui.label(stopwatch(monitor.elapsed_s)).classes("vc-h2 vc-muted").style("font-variant-numeric:tabular-nums")
                theme.progress_bar(overall)
                ui.label(monitor.message or "Aguardando").classes("vc-tiny vc-muted")
                if monitor.download is not None:
                    theme.progress_bar(monitor.download)
                for index, name in enumerate(STAGES):
                    done = monitor.stage > index or (monitor.stage == index and not studio.analyzing and not monitor.error)
                    current = monitor.stage == index and studio.analyzing
                    with ui.element("div").classes("vc-stage"):
                        ui.label("✓" if done else str(index + 1)).classes("vc-circle")
                        ui.label(name)
                        ui.space()
                        theme.pill("Pronto" if done else "Em análise" if current else "Na fila", "teal" if done else "")
                with ui.row().classes("mt-4 gap-3"):
                    if studio.analyzing:
                        cancel = theme.button("Cancelar análise", lambda: (monitor.cancel.set(), ui.notify("Cancelando após o passo atual…")))
                        if monitor.cancel.is_set():
                            cancel.disable()
                    elif project.report:
                        theme.button("Ver histórias sugeridas →", lambda: shell.go(STORIES), primary=True)
                    else:
                        theme.button("← Voltar ao material", lambda: shell.go(MATERIAL))
                if monitor.error:
                    ui.label(monitor.error).classes("vc-small bad mt-2")
            with theme.panel():
                ui.label("Takes").classes("vc-h3")
                for take in takes:
                    status = project.status.get(take.id)
                    stage = status.stage if status else "pendente"
                    with ui.row().classes("w-full items-center no-wrap gap-3 mt-2"):
                        ui.label(take.id).classes("vc-filetag")
                        ui.label(take.name).classes("vc-small").style("min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1")
                        theme.pill(STAGE_LABELS.get(stage, stage), "teal" if stage == STAGE_READY else "red" if stage == STAGE_FAILED else "")
                    theme.progress_bar(status.fraction if status else 0)
                    if status and status.error:
                        ui.label(status.error).classes("vc-tiny bad")
        with theme.stack():
            with theme.panel("accent"):
                theme.eyebrow("O que está emergindo")
                lines = monitor.log[-7:]
                if not lines:
                    ui.label("Falas e cenas aparecem aqui assim que forem encontradas.").classes("vc-muted vc-small mt-2")
                for line in lines:
                    ui.label(line).classes("vc-console")
            with theme.panel():
                ui.label("Se um take falhar").classes("vc-h3")
                ui.label("O lote continua. A proposta identifica o material não analisado e você pode tentar novamente; "
                         "o que já foi processado fica em cache.").classes("vc-muted vc-small")
            theme.note("Fatos observados primeiro, interpretação editorial depois. A análise pode concluir que falta material.")
