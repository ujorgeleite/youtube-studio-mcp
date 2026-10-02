"""Etapa 5: gerar o pacote para o Filmora, em background, com relatório em formação."""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter

from nicegui import run, ui

from core.keepawake import KEEP_AWAKE
from core.project import RenderRecord
from core.thermal import ThermalGovernor
from core.timefmt import clock, stopwatch
from montage.delivery import deliver
from montage.plan import ordered_beats

from . import power_view, theme, thermal_view
from .media import media_url
from .shell import Shell
from .state import REVIEW, STORIES

DONE, FAILED, RUNNING, QUEUED = "pronto", "falhou", "processando", "na_fila"
PACKAGE = (
    ("MP4 montado", "Vídeo completo para assistir e importar no Filmora."),
    ("Plano JSON", "Blocos, ordem, exclusões, faixas e referências aos originais."),
    ("Relatório editorial", "Mensagem, motivos, evidências, critérios e lacunas."),
    ("Legenda SRT", "Falas reposicionadas na timeline da montagem."),
    ("Timeline XML · a validar", "Final Cut Pro 7 XML para “Importar Timeline XML”; confirme na sua versão do Filmora."),
)


def chosen(shell: Shell):
    project = shell.studio.project
    return project.report.proposal(project.chosen) if project and project.report and project.chosen else None


async def process(shell: Shell) -> None:
    studio = shell.studio
    project = studio.project
    proposal = chosen(shell)
    inventory = studio.inventory
    if studio.busy or proposal is None or inventory is None or shell.refuse_if_working():
        return
    governor = ThermalGovernor(enabled=project.long_run)
    live = studio.delivery = {"running": True, "started": perf_counter(), "finished": 0.0, "fraction": {},
                              "message": "Preparando", "governor": governor}
    project.renders = {video.id: RenderRecord(video.id, QUEUED) for video in proposal.videos}
    shell.refresh()
    with KEEP_AWAKE:
        await render_videos(proposal, inventory, live, governor, project)
    live.update(running=False, finished=perf_counter(), message=" · ".join(filter(None, ["Entrega concluída", governor.summary()])))
    failures = sum(record.status == FAILED for record in project.renders.values())
    shell.notify("Entrega concluída." if not failures else f"{failures} vídeo(s) falharam; veja o relatório.",
                 "positive" if not failures else "warning")
    shell.refresh()


async def render_videos(proposal, inventory, live: dict, governor: ThermalGovernor, project) -> None:
    for video in proposal.videos:
        review = project.review.get(video.id)
        record = project.renders[video.id]
        record.status = RUNNING
        started = perf_counter()

        def progress(fraction: float, message: str, video_id: str = video.id) -> None:
            live["fraction"][video_id] = fraction
            live["message"] = message

        try:
            artifacts = await run.io_bound(
                deliver, proposal, video, inventory, review, project.layout.delivery(proposal.id, video.id),
                project.layout.work / "render", progress=progress, before_segment=governor.wait_if_hot,
            )
        except Exception as error:  # noqa: BLE001 - uma falha fica no vídeo; os outros continuam
            record.status, record.error = FAILED, str(error).splitlines()[0][:200]
        else:
            record.status, record.artifacts = DONE, artifacts
            record.duration_s = round(sum(beat.duration_s for beat in ordered_beats(video, review)), 2)
        record.seconds = round(perf_counter() - started, 1)
        project.save()


def open_in_finder(path: str) -> None:
    """Arquivos são revelados no Finder; pastas são abertas."""
    subprocess.run(["open", "-R", path] if Path(path).is_file() else ["open", path], check=False)


async def reveal(shell: Shell, path: str) -> None:
    shell.notify(f"Abrindo no Finder: {Path(path).name}")
    await run.io_bound(open_in_finder, path)


def show_video(shell: Shell, path: str, title: str) -> None:
    with shell.root, ui.dialog() as dialog, theme.panel().style("width:min(900px,calc(100vw - 35px))"):
        with ui.row().classes("w-full items-center"):
            theme.eyebrow("Montagem gerada")
            ui.space()
            theme.button("×", dialog.close, small=True)
        ui.label(title).classes("vc-h2")
        ui.video(media_url(path)).classes("w-full mt-2")
    dialog.open()


def render(shell: Shell) -> None:
    theme.title("05 / Entrega", "Da proposta para o Filmora",
                "Gere a montagem escolhida e mantenha as decisões disponíveis para continuar a edição.")
    proposal = chosen(shell)
    if proposal is None:
        with theme.panel():
            ui.label("Escolha e revise uma proposta antes de gerar a entrega.").classes("vc-muted")
            theme.button("← Histórias", lambda: shell.go(STORIES)).classes("mt-3")
        return

    @ui.refreshable
    def live() -> None:
        live_content(shell, proposal)

    live()
    shell.on_live(lambda: live.refresh() if shell.studio.delivery.get("running") else None)


def live_content(shell: Shell, proposal) -> None:
    studio = shell.studio
    project = studio.project
    state = studio.delivery
    running = bool(state.get("running"))
    records = project.renders
    done = sum(record.status == DONE for record in records.values())
    total = len(proposal.videos)
    plans = {video.id: ordered_beats(video, project.review.get(video.id)) for video in proposal.videos}
    empty = any(not beats for beats in plans.values())
    planned = sum(beat.duration_s for beats in plans.values() for beat in beats)
    fractions = [1.0 if records.get(video.id) and records[video.id].status in (DONE, FAILED) else state.get("fraction", {}).get(video.id, 0.0)
                 for video in proposal.videos]
    elapsed = ((state.get("finished") or perf_counter()) - state["started"]) if state.get("started") else 0.0
    finished = bool(records) and all(record.status in (DONE, FAILED) for record in records.values())
    with theme.layout():
        with theme.stack():
            with theme.panel("accent").style("text-align:center;padding:32px"):
                theme.eyebrow("Montagem concluída" if finished and not running else "Processamento local")
                ui.label(stopwatch(elapsed)).classes("vc-clock w-full")
                heading = "Montando imagem e áudio…" if running else "Entrega pronta" if finished else "Pronto para processar a proposta"
                ui.label(heading).classes("vc-h2 w-full")
                theme.progress_bar(sum(fractions) / len(fractions) if fractions else 0)
                ui.label(f"{done}/{total} vídeos · {clock(planned)} de montagem planejada").classes("vc-muted w-full")
                if running or finished:
                    ui.label(state.get("message", "")).classes("vc-tiny vc-muted w-full")
                if state.get("governor"):
                    with ui.column().classes("w-full items-center"):
                        thermal_view.render(state["governor"])
                        if running:
                            power_view.awake_badge(project)
                if empty:
                    ui.label("Uma saída ficou sem blocos. Volte à revisão e restaure pelo menos um.").classes("warn w-full")
                with ui.row().classes("w-full justify-center mt-4"):
                    button = theme.button("Processar novamente" if finished else "Processar →", lambda: process(shell), primary=True)
                    if running or empty:
                        button.disable()
                theme.note("Blocos já renderizados ficam em cache: reordenar e processar de novo só monta o que mudou.")
            for number, video in enumerate(proposal.videos, start=1):
                video_card(shell, number, video, plans[video.id], records.get(video.id), state.get("fraction", {}).get(video.id, 0.0))
        with theme.stack():
            with theme.panel():
                ui.label("Pacote de saída").classes("vc-h3")
                ui.label(str(project.layout.deliveries)).classes("vc-tiny vc-muted").style("word-break:break-all")
                for name, detail in PACKAGE:
                    with ui.column().classes("gap-0 w-full mt-3").style("border-top:1px solid var(--line);padding-top:10px"):
                        ui.label(name).classes("vc-small").style("font-weight:650")
                        ui.label(detail).classes("vc-tiny vc-muted")
                ui.label("✓ Originais preservados").classes("vc-small check mt-4")
                with ui.row().classes("gap-2 mt-3"):
                    back = theme.button("Voltar à revisão", lambda: shell.go(REVIEW), small=True)
                    if running:
                        back.disable()
                    theme.button("Abrir pasta", lambda: reveal(shell, str(project.layout.deliveries)), small=True)
            theme.note("A timeline editável precisa de um teste real de importação no Filmora; o MP4 é a entrega de referência.")


def video_card(shell: Shell, number: int, video, beats, record: RenderRecord | None, fraction: float) -> None:
    status = record.status if record else "proposta"
    labels = {DONE: ("Pronto", "teal"), FAILED: ("Falhou", "red"), RUNNING: (f"Processando {fraction * 100:.0f}%", ""),
              QUEUED: ("Na fila", ""), "proposta": ("Proposta", "")}
    label, tone = labels.get(status, (status, ""))
    with theme.panel("report" if status == DONE else ""):
        with ui.row().classes("w-full items-center"):
            ui.label(("✓ " if status == DONE else "") + f"Vídeo {number} · {video.title}").classes("vc-h3")
            ui.space()
            theme.pill(label, tone)
        with ui.element("div").classes("vc-metrics"):
            theme.metric(clock(sum(beat.duration_s for beat in beats)), "duração planejada")
            theme.metric(str(len(beats)), "blocos mantidos")
            theme.metric(str(sum(len(beat.overlays) for beat in beats)), "imagens de apoio")
        if status == RUNNING:
            theme.progress_bar(fraction)
        if record and record.error:
            ui.label(record.error).classes("vc-small bad")
        if record and record.artifacts:
            ui.label(f"Renderizado em {clock(record.seconds)} · {clock(record.duration_s)} de vídeo").classes("vc-tiny vc-muted")
            with ui.row().classes("gap-2 mt-2"):
                theme.button("▷ Assistir", lambda _, p=record.artifacts["video"]: show_video(shell, p, video.title), small=True)
                for key, name in (("video", "MP4"), ("report", "Relatório"), ("timeline", "Timeline XML"), ("subtitles", "SRT"), ("plan", "Plano")):
                    theme.button(name, lambda _, p=record.artifacts[key]: reveal(shell, p), small=True)
