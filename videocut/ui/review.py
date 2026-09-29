"""Etapa 4: revisar a sequência antes do render. Cada escolha é persistida na hora."""

from __future__ import annotations

from nicegui import ui

from core.project import ReviewState
from core.schema import PROBLEM, SPEECH, Beat, Proposal, StoryReport, StoryVideo
from core.serial import from_data, read_json
from core.timefmt import clock, span
from montage.plan import ordered_beats
from story.adjust import extend_beat, replace_moment, shorten, trim_beat

from . import theme
from .evidence import open_evidence
from .preview import play, player
from .shell import Shell
from .state import DELIVERY, STORIES


def selection(shell: Shell) -> tuple[Proposal, StoryVideo, ReviewState] | None:
    project = shell.studio.project
    proposal = project.report.proposal(project.chosen) if project and project.report and project.chosen else None
    if proposal is None or not proposal.videos:
        return None
    video = next((video for video in proposal.videos if video.id == shell.studio.video_id), proposal.videos[0])
    review = project.review.setdefault(video.id, ReviewState(order=[beat.id for beat in video.beats]))
    return proposal, video, review


def active_beat(video: StoryVideo, review: ReviewState) -> Beat:
    return next((beat for beat in video.beats if beat.id == review.active), video.beats[0])


def listed(video: StoryVideo, review: ReviewState) -> list[Beat]:
    """Todos os blocos na ordem da revisão, incluindo os excluídos."""
    return ordered_beats(video, ReviewState(order=review.order))


def save(shell: Shell) -> None:
    shell.studio.project.renders.clear()
    shell.studio.project.save()
    shell.main.refresh()


def move(shell: Shell, video: StoryVideo, review: ReviewState, beat_id: str, step: int) -> None:
    order = [beat.id for beat in listed(video, review)]
    index = order.index(beat_id)
    target = index + step
    if 0 <= target < len(order):
        order[index], order[target] = order[target], order[index]
        review.order = order
        save(shell)


def toggle(items: list[str], beat_id: str) -> None:
    items.remove(beat_id) if beat_id in items else items.append(beat_id)


def restore_original(shell: Shell, proposal: Proposal, video: StoryVideo) -> None:
    project = shell.studio.project
    data = read_json(project.layout.analysis / "historias.json")
    original = from_data(StoryReport, data).proposal(proposal.id) if data else None
    source = next((item for item in original.videos if item.id == video.id), None) if original else None
    if source is None:
        shell.notify("Não encontrei a proposta original salva.", "warning")
        return
    proposal.videos[proposal.videos.index(video)] = source
    project.review[video.id] = ReviewState(order=[beat.id for beat in source.beats], active=source.beats[0].id)
    save(shell)


def make_shorter(shell: Shell, proposal: Proposal, video: StoryVideo, review: ReviewState, minutes: float | None) -> None:
    inventory = shell.studio.inventory
    if not minutes or inventory is None:
        shell.notify("Informe a duração desejada em minutos.", "warning")
        return
    shorter = shorten(video, minutes * 60, inventory, set(review.excluded), set(review.protected))
    kept = {beat.id for beat in shorter.beats}
    proposal.videos[proposal.videos.index(video)] = shorter
    review.order = [beat_id for beat_id in review.order if beat_id in kept]
    review.excluded = [beat_id for beat_id in review.excluded if beat_id in kept]
    active = [beat for beat in shorter.beats if beat.id not in review.excluded]
    shell.notify(f"Versão com {clock(sum(beat.duration_s for beat in active))} · {len(video.beats) - len(shorter.beats)} bloco(s) removido(s).", "positive")
    save(shell)


def render(shell: Shell) -> None:
    theme.title("04 / Revisão", "A história, antes do render",
                "Veja de onde vem cada escolha, reorganize os blocos e preserve os momentos importantes.")
    chosen = selection(shell)
    if chosen is None:
        with theme.panel():
            ui.label("Escolha uma proposta primeiro.").classes("vc-muted")
            theme.button("← Histórias", lambda: shell.go(STORIES)).classes("mt-3")
        return
    proposal, video, review = chosen
    header(shell, proposal, video)
    with theme.layout():
        with theme.stack():
            preview_panel(shell, video, review)
            tracks_panel(shell, video, review)
            decision_panel(shell, video, review)
        with theme.stack():
            sequence_panel(shell, video, review)
            shorter_panel(shell, proposal, video, review)
            summary_panel(shell, proposal, video, review)


def header(shell: Shell, proposal: Proposal, video: StoryVideo) -> None:
    def pick(event) -> None:
        shell.studio.video_id = event.value
        shell.main.refresh()

    with ui.row().classes("w-full items-center gap-3 mb-4"):
        if proposal.multiple:
            ui.toggle({item.id: f"Vídeo {n} · {item.title}" for n, item in enumerate(proposal.videos, start=1)},
                      value=video.id, on_change=pick).props("no-caps unelevated toggle-color=teal-3 toggle-text-color=dark")
        else:
            ui.label(video.title).classes("vc-h3")
        ui.space()
        theme.button("Comparar propostas", lambda: shell.go(STORIES), small=True)
    if proposal.partial:
        theme.pill("Rascunho parcial · a mensagem precisa de material adicional", "amber").classes("mb-3")


def preview_panel(shell: Shell, video: StoryVideo, review: ReviewState) -> None:
    project = shell.studio.project
    takes = {take.id: take for take in project.takes}
    beat = active_beat(video, review)
    with ui.element("div").classes("w-full").style("border:1px solid #3b505c;border-radius:10px;overflow:hidden;background:#0c161f"):
        player("vc", "330px")
        with ui.row().classes("w-full items-center gap-3 p-3"):
            theme.button("▷ Bloco", lambda: play([beat], takes, project.layout), small=True)
            theme.button("▷ Sequência", lambda: play(ordered_beats(video, review), takes, project.layout), primary=True, small=True)
            with ui.column().classes("gap-0 flex-grow"):
                ui.label(f"{beat.take_id} · {beat.title}").classes("vc-small").style("font-weight:650")
                ui.label(f"{span(beat.start_s, beat.end_s)} · {beat.audio}").classes("vc-tiny vc-muted")
            theme.pill("Prévia sem render")


def tracks_panel(shell: Shell, video: StoryVideo, review: ReviewState) -> None:
    beats = ordered_beats(video, review)

    def select(beat_id: str) -> None:
        review.active = beat_id
        save(shell)

    with theme.panel():
        with ui.row().classes("w-full items-center"):
            ui.label("Imagem e fala em faixas separadas").classes("vc-h3")
            ui.space()
            ui.label(clock(sum(beat.duration_s for beat in beats))).classes("vc-tiny").style("font-family:monospace")
        if not beats:
            ui.label("Todos os blocos foram excluídos. Restaure um para continuar.").classes("vc-muted mt-3")
            return
        ui.label("Imagem · ordem dos blocos").classes("vc-pill mt-3")
        with ui.element("div").classes("vc-track"):
            for beat in beats:
                block = ui.label(beat.title).classes("vc-block").style(f"flex:{beat.duration_s:.2f}"
                                                                        + (";outline:2px solid var(--mint)" if beat.id == review.active else ""))
                block.on("click", lambda _, b=beat.id: select(b))
        ui.label("Apoio · imagens sobre a fala").classes("vc-pill")
        with ui.element("div").classes("vc-track"):
            for beat in beats:
                with ui.element("div").style(f"flex:{beat.duration_s:.2f};position:relative;height:42px"):
                    for overlay in beat.overlays:
                        left = overlay.at_s / beat.duration_s * 100
                        width = overlay.duration_s / beat.duration_s * 100
                        ui.label(overlay.take_id).classes("vc-block broll").style(f"position:absolute;left:{left:.1f}%;width:{width:.1f}%;min-width:0")
        ui.label("Áudio").classes("vc-pill")
        with ui.element("div").classes("vc-track"):
            for beat in beats:
                ui.label("Fala" if beat.audio == SPEECH else "Som ambiente").classes("vc-block " + ("audio" if beat.audio == SPEECH else "broll")).style(f"flex:{beat.duration_s:.2f}")
        theme.note("A fala continua enquanto as imagens de apoio aparecem por cima; o som ambiente delas entra baixo (−22 dB).")


def swap_dialog(shell: Shell, beat: Beat) -> None:
    inventory = shell.studio.inventory
    if inventory is None:
        shell.notify("Inventário da análise não encontrado.", "warning")
        return

    def apply(moment) -> None:
        replace_moment(beat, moment, inventory)
        dialog.close()
        save(shell)

    with shell.root, ui.dialog() as dialog, theme.panel().style("width:min(820px,calc(100vw - 35px));max-height:85vh;overflow:auto"):
        with ui.row().classes("w-full items-center"):
            theme.eyebrow(f"Trocar trecho / {beat.title}")
            ui.space()
            theme.button("×", dialog.close, small=True)
        ui.label("Escolha outro momento real do material").classes("vc-h2")
        for moment in inventory.moments:
            if moment.kind == PROBLEM:
                continue
            with ui.element("div").classes("vc-evidence"):
                ui.label(moment.id).classes("vc-filetag")
                with ui.column().classes("gap-0 flex-grow"):
                    ui.label(f"“{moment.speech[:140]}”" if moment.speech else moment.visual[:140]).classes("vc-small")
                    ui.label(f"{span(moment.start_s, moment.end_s)} · {moment.kind}").classes("vc-tiny vc-muted")
                theme.button("Usar", lambda _, m=moment: apply(m), small=True)
    dialog.open()


def decision_panel(shell: Shell, video: StoryVideo, review: ReviewState) -> None:
    inventory = shell.studio.inventory
    beat = active_beat(video, review)

    def change(action) -> None:
        if inventory is None or not action(beat, inventory):
            shell.notify("Não há frase disponível para essa mudança.", "warning")
            return
        save(shell)

    with theme.panel():
        theme.eyebrow(f"Decisão selecionada / {beat.title} · {beat.role}")
        if beat.reason:
            ui.label(beat.reason).classes("mt-2")
        for evidence in beat.evidence:
            if evidence.quote:
                ui.label(f"“{evidence.quote}”").classes("vc-small mt-2")
            if evidence.observation:
                ui.label(f"Imagem: {evidence.observation}").classes("vc-tiny vc-muted")
        with ui.row().classes("gap-2 mt-3"):
            if beat.evidence:
                theme.button("Conferir evidência no take ↗", lambda: open_evidence(shell, beat.evidence[0], beat.reason), small=True)
            if beat.audio == SPEECH:
                theme.button("+ frase", lambda: change(extend_beat), small=True)
                theme.button("− frase", lambda: change(trim_beat), small=True)
            theme.button("Trocar trecho…", lambda: swap_dialog(shell, beat), small=True)


def sequence_panel(shell: Shell, video: StoryVideo, review: ReviewState) -> None:
    beats = listed(video, review)
    active = [beat for beat in beats if beat.id not in review.excluded]

    def act(items: list[str], beat_id: str) -> None:
        toggle(items, beat_id)
        save(shell)

    def view(beat_id: str) -> None:
        review.active = beat_id
        save(shell)

    with ui.row().classes("w-full items-center"):
        ui.label("Sequência proposta").classes("vc-h3")
        ui.space()
        ui.label(f"{len(active)} blocos ativos").classes("vc-tiny vc-muted")
    for number, beat in enumerate(beats, start=1):
        excluded = beat.id in review.excluded
        protected = beat.id in review.protected
        classes = "vc-beat" + (" selected" if beat.id == review.active else "") + (" excluded" if excluded else "")
        with ui.element("section").classes(classes):
            with ui.row().classes("w-full items-center no-wrap"):
                ui.label(f"{number:02d} / {beat.title}").classes("vc-small").style("font-weight:650")
                ui.space()
                if protected:
                    theme.pill("Protegido", "teal")
                ui.label(clock(beat.duration_s)).classes("vc-tiny vc-muted")
            ui.label(f"{beat.take_id} · {span(beat.start_s, beat.end_s)} · {beat.role}"
                     + (f" · {len(beat.overlays)} apoio" if beat.overlays else "")).classes("vc-tiny vc-muted")
            with ui.row().classes("gap-1 mt-2"):
                theme.button("Ver", lambda _, b=beat.id: view(b), small=True)
                theme.button("Restaurar" if excluded else "Excluir", lambda _, b=beat.id: act(review.excluded, b), small=True)
                theme.button("↑", lambda _, b=beat.id: move(shell, video, review, b, -1), small=True).props(f"aria-label='Mover {beat.title} para cima'")
                theme.button("↓", lambda _, b=beat.id: move(shell, video, review, b, 1), small=True).props(f"aria-label='Mover {beat.title} para baixo'")
                theme.button("Desproteger" if protected else "Proteger", lambda _, b=beat.id: act(review.protected, b), small=True)


def shorter_panel(shell: Shell, proposal: Proposal, video: StoryVideo, review: ReviewState) -> None:
    current = sum(beat.duration_s for beat in ordered_beats(video, review))
    with theme.panel():
        ui.label("Versão mais curta").classes("vc-h3")
        ui.label("Recalcula na hora, sem analisar de novo: tira blocos de apoio primeiro e mantém gancho, "
                 "mensagem, conclusão e blocos protegidos.").classes("vc-tiny vc-muted")
        target = ui.number("Duração alvo (min)", value=round(max(0.5, current * 0.75 / 60), 1), min=0.5, step=0.5).classes("vc-field w-full mt-2").props("outlined dense")
        with ui.row().classes("gap-2 mt-3"):
            theme.button("Gerar versão mais curta", lambda: make_shorter(shell, proposal, video, review, target.value), small=True)
            theme.button("Restaurar original", lambda: restore_original(shell, proposal, video), small=True)


def summary_panel(shell: Shell, proposal: Proposal, video: StoryVideo, review: ReviewState) -> None:
    with theme.panel():
        theme.eyebrow("Prévia da entrega")
        with ui.element("div").classes("vc-metrics").style("grid-template-columns:1fr 1fr"):
            theme.metric(clock(sum(beat.duration_s for beat in ordered_beats(video, review))), "vídeo selecionado")
            theme.metric(str(len(proposal.videos)), "vídeos planejados")
        theme.button("Preparar entrega →", lambda: shell.go(DELIVERY), primary=True).classes("w-full")
        theme.note("As escolhas ficam salvas no projeto: trocar de vídeo, voltar às propostas ou fechar o app não as perde.")
