"""Configurações: prompts e regras editáveis, skills, agentes e registro do que foi enviado à IA."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from nicegui import run, ui

from core import settings
from core.extensions import AGENTS, SKILL_STAGES, SKILLS, Extension
from story.agents import AGENT_VARIABLES, results, unknown_variables

from . import theme
from .shell import Shell

LANGUAGE = {settings.PROMPT: "Markdown", settings.YAML: "YAML"}
TABS = ("Prompts e regras", "Skills", "Agentes", "Registro de chamadas")
EDITOR_STYLE = "height:430px;border:1px solid var(--line);border-radius:8px;overflow:hidden"


def render(shell: Shell) -> None:
    studio = shell.studio
    theme.title("Configurações", "O que a IA recebe, e como",
                "Edite os pedidos enviados aos modelos, as regras do canal e do estilo de cena, crie skills e agentes "
                "e confira o registro de cada chamada. O padrão do repositório nunca é perdido.")
    current = studio.settings.get("tab", TABS[0])

    def pick(tab: str) -> None:
        studio.settings["tab"] = tab
        shell.main.refresh()

    with ui.row().classes("gap-2 mb-4"):
        for tab in TABS:
            theme.button(tab, lambda _, t=tab: pick(t), primary=tab == current, small=True)
    {TABS[0]: prompts_tab, TABS[1]: skills_tab, TABS[2]: agents_tab, TABS[3]: log_tab}[current](shell)


def prompts_tab(shell: Shell) -> None:
    studio = shell.studio
    key = studio.settings.get("key", settings.EDITABLES[0].key)
    item = settings.editable(key)

    def select(new_key: str) -> None:
        studio.settings["key"] = new_key
        shell.main.refresh()

    with theme.layout().style("grid-template-columns:minmax(230px,1fr) minmax(0,3fr)"):
        with theme.stack():
            group = None
            with theme.panel():
                for option in settings.EDITABLES:
                    if option.group != group:
                        group = option.group
                        theme.eyebrow(group).classes("mt-3")
                    with ui.row().classes("w-full items-center no-wrap gap-2 mt-1"):
                        ui.button(option.label, on_click=lambda _, k=option.key: select(k), color=None) \
                            .props("flat dense no-caps align=left").classes("flex-grow vc-small") \
                            .style("color:var(--mint)" if option.key == key else "")
                        if settings.is_customized(option.key):
                            theme.pill("editado", "teal")
        with theme.stack():
            editor_panel(shell, item)


def editor_panel(shell: Shell, item: settings.Editable) -> None:
    project = shell.studio.project
    with theme.panel():
        with ui.row().classes("w-full items-center"):
            ui.label(item.label).classes("vc-h3")
            ui.space()
            theme.pill("editado" if settings.is_customized(item.key) else "padrão", "teal" if settings.is_customized(item.key) else "")
        ui.label(item.description).classes("vc-small vc-muted")
        ui.label(settings.IMPACT[item.affects]).classes("vc-tiny warn")
        if item.required:
            with ui.row().classes("gap-1 mt-2"):
                ui.label("Variáveis preenchidas pelo app:").classes("vc-tiny vc-muted")
                for name in item.required:
                    ui.label("{" + name + "}").classes("vc-filetag")
        editor = ui.codemirror(settings.read(item.key), language=LANGUAGE[item.kind], theme="vscodeDark", line_wrapping=True) \
            .classes("w-full mt-3").style(EDITOR_STYLE)
        status = ui.label(f"~{settings.estimate_tokens(editor.value)} tokens").classes("vc-tiny vc-muted mt-1")
        errors_box = ui.column().classes("gap-0 mt-1")

        def check() -> list[str]:
            errors = settings.validate(item.key, editor.value)
            errors_box.clear()
            with errors_box:
                for error in errors:
                    ui.label(error).classes("vc-tiny bad")
            status.text = f"~{settings.estimate_tokens(editor.value)} tokens" + (" · pronto para salvar" if not errors else "")
            return errors

        editor.on_value_change(lambda _: check())

        def save() -> None:
            errors = settings.save(item.key, editor.value)
            if errors:
                check()
                shell.notify("Não salvei: corrija os itens em vermelho.", "warning")
                return
            shell.notify(f"“{item.label}” salvo. {settings.IMPACT[item.affects]}", "positive")
            shell.main.refresh()

        def restore() -> None:
            settings.restore_default(item.key)
            shell.notify(f"“{item.label}” voltou ao padrão. A versão editada ficou no histórico.")
            shell.main.refresh()

        with ui.row().classes("gap-2 mt-3"):
            theme.button("Salvar", save, primary=True, small=True)
            theme.button("Prévia com o projeto aberto", lambda: preview_dialog(shell, item, editor.value), small=True)
            theme.button("Comparar com o padrão", lambda: diff_dialog(shell, item, editor.value), small=True)
            theme.button("Histórico", lambda: history_dialog(shell, item, editor), small=True)
            if settings.is_customized(item.key):
                theme.button("Restaurar padrão", restore, small=True)
        if project is None:
            theme.note("Abra um projeto analisado para ver a prévia com dados reais.")


def dialog_panel(shell: Shell, width: int = 900):
    dialog = ui.dialog()
    with shell.root, dialog:
        panel = theme.panel().style(f"width:min({width}px,calc(100vw - 35px));max-height:88vh;overflow:auto")
    return dialog, panel


def preview_dialog(shell: Shell, item: settings.Editable, text: str) -> None:
    from .settings_preview import build_preview

    errors = settings.validate(item.key, text)
    content = "\n".join(errors) if errors else build_preview(shell.studio, item.key, text)
    dialog, panel = dialog_panel(shell)
    with panel:
        theme.eyebrow(f"Prévia / {item.label}")
        ui.label(f"~{settings.estimate_tokens(content)} tokens · é exatamente isto que o modelo recebe").classes("vc-small vc-muted")
        ui.codemirror(content, language=LANGUAGE[settings.PROMPT], theme="vscodeDark", line_wrapping=True) \
            .classes("w-full mt-2").style("height:60vh").props("readonly")
        theme.button("Fechar", dialog.close, small=True).classes("mt-3")
    dialog.open()


def diff_dialog(shell: Shell, item: settings.Editable, text: str) -> None:
    diff = "\n".join(difflib.unified_diff(settings.read_default(item.key).splitlines(), text.splitlines(),
                                          "padrão", "atual", lineterm="")) or "Sem diferenças em relação ao padrão."
    dialog, panel = dialog_panel(shell)
    with panel:
        theme.eyebrow(f"Diferenças / {item.label}")
        ui.codemirror(diff, theme="vscodeDark", line_wrapping=True).classes("w-full mt-2").style("height:60vh")
        theme.button("Fechar", dialog.close, small=True).classes("mt-3")
    dialog.open()


def history_dialog(shell: Shell, item: settings.Editable, editor) -> None:
    versions = settings.history(item.key)
    dialog, panel = dialog_panel(shell, 640)

    def load(path: Path) -> None:
        editor.value = path.read_text(encoding="utf-8")
        dialog.close()
        shell.notify("Versão carregada no editor. Clique em Salvar para usá-la.")

    with panel:
        theme.eyebrow(f"Histórico / {item.label}")
        if not versions:
            ui.label("Nenhuma versão anterior salva ainda.").classes("vc-muted mt-2")
        for path in versions[:30]:
            with ui.row().classes("w-full items-center mt-2"):
                ui.label(path.stem).classes("vc-small").style("font-family:monospace")
                ui.space()
                theme.button("Carregar no editor", lambda _, p=path: load(p), small=True)
        theme.button("Fechar", dialog.close, small=True).classes("mt-3")
    dialog.open()


def extension_editor(shell: Shell, registry, extension: Extension | None, kind: str) -> None:
    """Formulário comum a skills e agentes."""
    dialog, panel = dialog_panel(shell)
    with panel:
        theme.eyebrow(("Editar " if extension else "Nova ") + kind)
        name = ui.input("Nome", value=extension.name if extension else "").classes("vc-field w-full").props("outlined dense")
        description = ui.input("Descrição (uma linha)", value=extension.description if extension else "") \
            .classes("vc-field w-full mt-2").props("outlined dense")
        stages = None
        if registry is SKILLS:
            stages = ui.select({stage: f"Planejador · {stage}" for stage in SKILL_STAGES}, multiple=True, label="Etapas",
                               value=list(extension.stages) if extension and extension.stages else list(SKILL_STAGES)) \
                .classes("vc-field w-full mt-2").props("outlined dense")
            ui.label("O texto abaixo é acrescentado ao pedido dessas etapas quando a skill está ativa no projeto.").classes("vc-tiny vc-muted mt-2")
        else:
            ui.label("Variáveis disponíveis: " + ", ".join("{" + name + "}" for name in AGENT_VARIABLES)
                     + ". A resposta é salva como Markdown em analise/agentes/.").classes("vc-tiny vc-muted mt-2")
        body = ui.codemirror(extension.body if extension else "", language="Markdown", theme="vscodeDark", line_wrapping=True) \
            .classes("w-full mt-2").style("height:320px")

        def save() -> None:
            if registry is AGENTS and (unknown := unknown_variables(body.value)):
                shell.notify("Variáveis desconhecidas: " + ", ".join(unknown), "warning")
                return
            try:
                extra = {"etapas": list(stages.value)} if stages is not None else {}
                registry.save(name.value, description.value, body.value, key=extension.key if extension else None, **extra)
            except ValueError as error:
                shell.notify(str(error), "warning")
                return
            dialog.close()
            shell.notify(f"{kind.capitalize()} salva.", "positive")
            shell.main.refresh()

        with ui.row().classes("gap-2 mt-3"):
            theme.button("Salvar", save, primary=True, small=True)
            theme.button("Cancelar", dialog.close, small=True)
    dialog.open()


def extension_row(shell: Shell, registry, extension: Extension, kind: str, actions) -> None:
    with ui.element("section").classes("vc-beat"):
        with ui.row().classes("w-full items-center no-wrap"):
            ui.label(extension.name).classes("vc-small").style("font-weight:650")
            ui.space()
            theme.pill("padrão" if extension.builtin else "sua", "" if extension.builtin else "teal")
        if extension.description:
            ui.label(extension.description).classes("vc-tiny vc-muted")
        with ui.row().classes("gap-1 mt-2 items-center"):
            actions()
            theme.button("Editar", lambda: extension_editor(shell, registry, extension, kind), small=True)
            if not extension.builtin:
                def remove() -> None:
                    registry.remove(extension.key)
                    shell.notify(f"{kind.capitalize()} “{extension.name}” removida.")
                    shell.main.refresh()
                theme.button("Remover", remove, small=True)


def skills_tab(shell: Shell) -> None:
    project = shell.studio.project

    def toggle(key: str, value: bool) -> None:
        active = set(project.skills)
        active.add(key) if value else active.discard(key)
        project.skills = sorted(active)
        project.save()
        shell.notify("Skills atualizadas. Clique em “Refazer histórias” para aplicar.")

    with theme.panel():
        with ui.row().classes("w-full items-center"):
            ui.label("Skills").classes("vc-h3")
            ui.space()
            theme.button("Nova skill", lambda: extension_editor(shell, SKILLS, None, "skill"), small=True)
        ui.label("Instruções reutilizáveis que mudam como o planejador escolhe os trechos. Ative por projeto.").classes("vc-small vc-muted")
        for skill in SKILLS.all():
            def actions(skill=skill) -> None:
                if project:
                    ui.switch("Ativa neste projeto", value=skill.key in project.skills,
                              on_change=lambda event, k=skill.key: toggle(k, bool(event.value))).props("color=teal-3 dense")
                ui.label(" · ".join(skill.stages) if skill.stages else "todas as etapas").classes("vc-tiny vc-muted")
            extension_row(shell, SKILLS, skill, "skill", actions)
        if project is None:
            theme.note("Abra um projeto para ativar skills nele.")


def agents_tab(shell: Shell) -> None:
    from .agents_runner import run_selected_agents

    studio = shell.studio
    project = studio.project
    proposal = project.report.proposal(project.chosen) if project and project.report and project.chosen else None
    video = proposal.videos[0] if proposal else None
    with theme.panel():
        with ui.row().classes("w-full items-center"):
            ui.label("Agentes").classes("vc-h3")
            ui.space()
            theme.button("Novo agente", lambda: extension_editor(shell, AGENTS, None, "agente"), small=True)
        ui.label("Etapas extras que leem a montagem escolhida e devolvem texto (títulos, revisão de ritmo, checagem). "
                 "Nunca alteram a montagem.").classes("vc-small vc-muted")
        for agent in AGENTS.all():
            def actions(agent=agent) -> None:
                if video:
                    theme.button("Rodar agora", lambda: run_selected_agents(shell, [agent.key], video.id), primary=True, small=True)
            extension_row(shell, AGENTS, agent, "agente", actions)
        if video is None:
            theme.note("Escolha uma proposta na etapa Histórias para rodar agentes sobre ela.")
    if video and project:
        with theme.panel():
            ui.label(f"Resultados · {video.title}").classes("vc-h3")
            outputs = results(project.layout.analysis / "agentes", video.id)
            if not outputs:
                ui.label("Nenhum agente rodou ainda para este vídeo.").classes("vc-muted vc-small")
            for path in outputs:
                with ui.expansion(path.stem.split("__")[0]).classes("w-full vc-small"):
                    ui.markdown(path.read_text(encoding="utf-8"))


def log_tab(shell: Shell) -> None:
    project = shell.studio.project
    folder = project.layout.analysis / "registro" if project else None
    runs = sorted(folder.glob("*.jsonl"), reverse=True) if folder and folder.is_dir() else []
    with theme.panel():
        ui.label("Registro de chamadas").classes("vc-h3")
        ui.label("Cada pedido enviado ao modelo e a resposta recebida, por execução. Use para ver o que a IA "
                 "entendeu e ajustar prompts, regras e skills.").classes("vc-small vc-muted")
        if not runs:
            ui.label("Nenhum registro ainda neste projeto. Ele é criado na próxima análise, “Refazer histórias” ou agente.").classes("vc-muted mt-2")
            return
        chosen = shell.studio.settings.get("log") or runs[0].name
        ui.select({path.name: path.stem for path in runs}, value=chosen if chosen in {p.name for p in runs} else runs[0].name,
                  label="Execução", on_change=lambda event: (shell.studio.settings.update(log=event.value), shell.main.refresh())) \
            .classes("vc-field w-full mt-2").props("outlined dense")
        records = [json.loads(line) for line in (folder / chosen).read_text(encoding="utf-8").splitlines() if line.strip()] \
            if (folder / chosen).is_file() else []
        total = sum(record.get("segundos", 0) for record in records)
        ui.label(f"{len(records)} chamadas · {total:.0f} s no modelo").classes("vc-tiny vc-muted mt-2")
        for number, record in enumerate(records, start=1):
            title = f"{number:03d} · {record.get('etapa', '')[:70]} · {record.get('segundos', 0)} s · ~{settings.estimate_tokens(record.get('prompt', ''))} tokens"
            with ui.expansion(title).classes("w-full vc-small"):
                if record.get("imagens"):
                    ui.label("Imagens: " + ", ".join(record["imagens"])).classes("vc-tiny vc-muted")
                ui.label("Pedido").classes("vc-eyebrow mt-2")
                ui.code(record.get("prompt", "")).classes("w-full")
                ui.label("Resposta").classes("vc-eyebrow mt-2")
                ui.code(record.get("resposta", "")).classes("w-full")
