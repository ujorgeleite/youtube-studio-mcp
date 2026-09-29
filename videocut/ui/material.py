"""Etapa 1: escolher a pasta, os takes e o que se quer contar."""

from __future__ import annotations

from pathlib import Path

from nicegui import run, ui

from core.config import load_yaml, min_take_s, models, vision_options
from core.project import Project, default_output_dir
from core.safety import SourceProtectionError
from core.thermal import LongRunConfig
from core.timefmt import clock
from media.catalog import catalog_folder
from media.probe import MediaError, list_videos

from . import memory_view, power_view, theme
from .analysis_view import start_analysis
from .filepicker import choose_directory
from .media import media_url
from .shell import Shell
from .state import STORIES


async def open_folder(shell: Shell, folder: str, output: str) -> None:
    studio = shell.studio
    if not folder.strip():
        shell.notify("Informe a pasta com os takes.", "warning")
        return
    if shell.refuse_if_working():
        return
    try:
        project = Project.open(folder.strip(), output.strip() or None)
    except SourceProtectionError as error:
        shell.notify(str(error), "negative")
        return
    try:
        with shell.activity(f"Carregando {Path(project.folder).name}") as step:
            step("Listando vídeos da pasta")
            takes, errors = await run.io_bound(catalog_folder, project.folder, project.layout.thumbnails, project.takes, step)
            step(f"{len(takes)} vídeo(s) prontos" + (f" · {len(errors)} ignorado(s)" if errors else ""), 1.0)
    except MediaError as error:
        shell.notify(str(error), "negative")
        return
    skipped = project.merge_takes(takes, min_take_s())
    project.save()
    if skipped:
        shell.notify(f"{len(skipped)} take(s) com menos de {min_take_s():g} s ficaram desmarcados · marque-os se quiser analisar.")
    studio.use(project)
    studio.catalog_errors = errors
    if not takes:
        shell.notify("Nenhum vídeo encontrado nesta pasta.", "warning")
    shell.refresh()


def empty_folder_message(project: Project) -> str:
    """Projeto reaberto sem catálogo salvo não é o mesmo que pasta vazia."""
    try:
        count = len(list_videos(project.folder))
    except MediaError:
        return "A pasta de origem não foi encontrada. Escolha a pasta de novo."
    if count:
        return f"{count} vídeo(s) nesta pasta ainda não foram lidos. Clique em Carregar."
    return "Nenhum vídeo encontrado nesta pasta."


def render(shell: Shell) -> None:
    studio = shell.studio
    project = studio.project
    theme.title("01 / Material", "Que história existe nos seus takes?",
                "Comece pelos originais. A análise vai cruzar o que aparece com o que é dito.")
    with theme.layout():
        with theme.stack():
            source_panel(shell)
            if project and project.takes:
                take_grid(shell)
            elif project:
                with theme.panel():
                    ui.label(empty_folder_message(project)).classes("vc-muted")
        with theme.stack():
            if project and project.takes:
                intention_panel(shell)
                execution_panel(shell)
            memory_view.memory_panel(shell, project.model if project else None)
            with theme.panel():
                theme.eyebrow("Uma decisão de cada vez")
                ui.label("Primeiro entender o material. Depois escolher a história. Só então montar.").classes("vc-muted vc-small")


def source_panel(shell: Shell) -> None:
    project = shell.studio.project
    with theme.panel():
        with ui.row().classes("w-full items-end gap-3 no-wrap"):
            folder = ui.input("Pasta raw", value=project.folder if project else "").classes("vc-field flex-grow").props("outlined dense")
            output = ui.input("Saída", value=project.output_dir if project else "").classes("vc-field flex-grow").props("outlined dense")

            async def browse() -> None:
                if shell.refuse_if_working():
                    return
                with shell.activity("Escolhendo a pasta") as step:
                    step("Selecione a pasta no Finder (a janela pode abrir atrás do navegador)")
                    chosen = await run.io_bound(choose_directory)
                    step(chosen or "Nenhuma pasta escolhida")
                if chosen:
                    folder.value = chosen.rstrip("/")
                    output.value = str(default_output_dir(folder.value))
                    await open_folder(shell, folder.value, output.value)

            theme.button("Escolher pasta…", browse)
            theme.button("Carregar", lambda: open_folder(shell, folder.value, output.value))
        theme.note("Os originais nunca são alterados. Proxies .LRF da câmera com o mesmo nome são usados para "
                   "visualizar e analisar; a montagem final lê os arquivos originais.")
        for name, error in shell.studio.catalog_errors.items():
            ui.label(f"{name}: {error}").classes("vc-tiny bad")
        if project and project.report:
            with ui.row().classes("w-full items-center mt-3"):
                theme.pill("Análise anterior encontrada", "teal")
                ui.label(f"{len(project.report.proposals)} proposta(s) salvas").classes("vc-tiny vc-muted")
                ui.space()
                theme.button("Ver histórias →", lambda: shell.go(STORIES), small=True)


def _selected_summary(project: Project) -> str:
    total = sum(take.duration_s for take in project.selected_takes)
    short = [take for take in project.short_takes(min_take_s()) if take.id not in project.selected]
    extra = f" · {len(short)} curto(s) fora da análise" if short else ""
    return f"{len(project.selected)} selecionados · {clock(total)} de material{extra}"


def take_grid(shell: Shell) -> None:
    project = shell.studio.project

    def toggle(take_id: str, value: bool) -> None:
        chosen = set(project.selected)
        chosen.add(take_id) if value else chosen.discard(take_id)
        project.selected = [take.id for take in project.takes if take.id in chosen]
        project.save()
        shell.main.refresh()

    def set_all(value: bool) -> None:
        project.selected = [take.id for take in project.takes] if value else []
        project.save()
        shell.main.refresh()

    def drop_short() -> None:
        short = {take.id for take in project.short_takes(limit)}
        removed = [take_id for take_id in project.selected if take_id in short]
        project.selected = [take_id for take_id in project.selected if take_id not in short]
        project.save()
        shell.notify(f"{len(removed)} take(s) curto(s) desmarcado(s)." if removed else "Nenhum take curto estava marcado.")
        shell.main.refresh()

    limit = min_take_s()

    with ui.row().classes("w-full justify-between items-center"):
        ui.label(f"{len(project.takes)} takes").classes("vc-h3")
        with ui.row().classes("gap-2"):
            theme.button("Todos", lambda: set_all(True), small=True)
            theme.button("Limpar", lambda: set_all(False), small=True)
            if project.short_takes(limit):
                theme.button(f"Desmarcar curtos (< {limit:g} s)", drop_short, small=True)
    with ui.element("div").classes("vc-grid"):
        for take in project.takes:
            checked = take.id in project.selected
            with ui.element("article").classes("vc-take" + (" checked" if checked else "")):
                with ui.element("div").classes("vc-thumb"):
                    if take.thumbnail and Path(take.thumbnail).is_file():
                        ui.image(media_url(take.thumbnail)).classes("w-full h-full")
                    ui.label(clock(take.duration_s)).classes("vc-duration")
                with ui.column().classes("p-3 gap-1"):
                    ui.checkbox(f"{take.id} · {take.name}", value=checked,
                                on_change=lambda event, take_id=take.id: toggle(take_id, event.value)).classes("vc-small")
                    with ui.row().classes("gap-2 items-center"):
                        ui.label(f"{take.width}×{take.height} · {take.fps:g} fps").classes("vc-tiny vc-muted")
                        if take.proxy:
                            theme.pill("LRF", "teal")
                        if not take.has_audio:
                            theme.pill("sem áudio", "amber")
                        if take.duration_s < limit:
                            theme.pill(f"curto · {take.duration_s:.0f} s", "amber")
    ui.label(_selected_summary(project)).classes("vc-tiny vc-muted")


def intention_panel(shell: Shell) -> None:
    project = shell.studio.project
    formats = load_yaml("canal.yaml").get("formatos", {"auto": "Deixar o sistema sugerir"})
    options = {key: value["label"] for key, value in vision_options().items()}
    default_model = models().get("vision", {}).get("default")

    def update(field: str, value) -> None:
        setattr(project, field, value)
        project.save()

    with theme.panel():
        ui.label("Sua intenção orienta a proposta").classes("vc-h3")
        ui.textarea("O que você queria contar? (opcional)", value=project.intention,
                    on_change=lambda event: update("intention", event.value or "")).classes("vc-field w-full").props("outlined autogrow")
        ui.label("Sem uma intenção, o sistema sugere temas a partir do material.").classes("vc-tiny vc-muted")
        ui.select({key: value.split(" — ")[0] for key, value in formats.items()}, label="Formato editorial",
                  value=project.format if project.format in formats else "auto",
                  on_change=lambda event: update("format", event.value)).classes("vc-field w-full mt-3").props("outlined dense")
        ui.number("Duração desejada (min, opcional)", value=project.target_minutes, min=0.5, step=0.5,
                  on_change=lambda event: update("target_minutes", event.value or None)).classes("vc-field w-full mt-3").props("outlined dense")
        def pick_model(value: str) -> None:
            update("model", value)
            shell.main.refresh()

        ui.select(options, label="Modelo visual local", value=project.model or default_model,
                  on_change=lambda event: pick_model(event.value)).classes("vc-field w-full mt-3").props("outlined dense")
        with ui.column().classes("gap-1 mt-4"):
            ui.label("O que você recebe").classes("vc-h3")
            ui.label("✓ Inventário de falas e imagens\n✓ Propostas de um ou vários vídeos\n✓ Lacunas e evidências de cada ideia").classes("vc-small").style("white-space:pre-line")
        start = theme.button("Analisar conteúdo →", lambda: start_analysis(shell), primary=True).classes("w-full mt-4")
        if not project.selected:
            start.disable()
        theme.note("Na primeira análise os modelos são baixados do Hugging Face (Whisper ~1,6 GB; "
                   "Qwen3-VL 4B ~3,1 GB ou 8B ~5,8 GB), com progresso na tela. Para baixar antes: make models.")


def execution_panel(shell: Shell) -> None:
    project = shell.studio.project
    limits = LongRunConfig.load()

    def toggle(field: str, value: bool) -> None:
        setattr(project, field, value)
        project.save()
        shell.main.refresh()

    with theme.panel():
        ui.label("Execução").classes("vc-h3")
        ui.switch("Modo de cargas longas", value=project.long_run,
                  on_change=lambda event: toggle("long_run", bool(event.value))).props("color=teal-3")
        ui.label(f"Pausa entre etapas quando o Mac passa de {limits.pause_temp_c:g} °C ou o macOS indica “sério”, "
                 f"e retoma abaixo de {limits.resume_temp_c:g} °C. Use em análises e renders longos.").classes("vc-tiny vc-muted")
        ui.switch("Rodar de madrugada", value=project.overnight,
                  on_change=lambda event: toggle("overnight", bool(event.value))).props("color=teal-3").classes("mt-3")
        ui.label("Mantém o Mac e o disco acordados durante o trabalho (a tela pode apagar) e confere os ajustes "
                 "de energia. Nada no macOS é alterado nem pede senha.").classes("vc-tiny vc-muted")
        if project.overnight:
            with ui.column().classes("w-full gap-0 mt-2"):
                power_view.overnight_checklist()
            if not project.long_run:
                with ui.row().classes("items-center gap-2 mt-2"):
                    ui.label("Sugestão: ligue também o modo de cargas longas para o Mac esfriar entre etapas.").classes("vc-tiny warn")
                    theme.button("Ligar", lambda: toggle("long_run", True), small=True)
