from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from silence.analyze import extract_thumbnail, list_videos, probe_duration
from smartcut.config import CutRules, list_presets, load_rules
from smartcut.cuts import cuts_from_words
from smartcut.pipeline import analyze_clip, default_output_dir
from smartcut.preprocess import extract_audio, normalize_loudness
from smartcut.render import render_with_handles
from .filepicker import choose_directory

MEDIA: dict[str, str] = {}
THUMB_DIR = Path(__file__).resolve().parents[1] / ".smartcut-cache" / "thumbnails"


def _key(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:20]


@app.get("/media/{key}")
def media(key: str):
    path = MEDIA.get(key)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


def _clock(seconds: float, *, brief: bool = False) -> str:
    minutes, secs = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{minutes}:{secs:04.1f}" if brief and not hours else f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _context(plan, cut) -> str:
    before = [word.text for word in plan.words if cut.start_s - 3 <= word.end_s <= cut.start_s]
    after = [word.text for word in plan.words if cut.end_s <= word.start_s <= cut.end_s + 3]
    return f"…{' '.join(before[-5:])}  ···  {' '.join(after[:5])}…"


def _timeline(plan, duration: float, active_cut: int | None) -> dict:
    words = [[word.start_s, max(.035, word.end_s - word.start_s)] for word in plan.words]
    cut_data = [[{"xAxis": cut.start_s}, {"xAxis": cut.end_s}] for cut in plan.cuts]
    protected = [[{"xAxis": pause.start_s}, {"xAxis": pause.end_s}] for pause in plan.protected_pauses]
    series = [{"name": "fala mantida", "type": "bar", "data": words, "barWidth": 3,
               "itemStyle": {"color": "#2dd4bf", "borderRadius": 1}, "silent": True,
               "markArea": {"silent": True, "itemStyle": {"color": "rgba(251,113,133,.48)"}, "data": cut_data}}]
    if protected:
        series.append({"name": "pausa protegida", "type": "line", "data": [], "silent": True,
                       "markArea": {"silent": True, "itemStyle": {"color": "rgba(251,191,36,.32)"}, "data": protected}})
    if active_cut is not None and active_cut < len(plan.cuts):
        cut = plan.cuts[active_cut]
        series.append({"type": "line", "data": [], "silent": True,
                       "markArea": {"itemStyle": {"color": "rgba(59,130,246,.22)"}, "data": [[{"xAxis": cut.start_s}, {"xAxis": cut.end_s}]]}})
    return {"animation": False, "backgroundColor": "transparent", "grid": {"left": 8, "right": 8, "top": 22, "bottom": 30},
            "xAxis": {"type": "value", "min": 0, "max": max(duration, 1), "axisLabel": {"color": "#94a3b8", "formatter": "{value}s"}, "axisLine": {"lineStyle": {"color": "#334155"}}},
            "yAxis": {"show": False, "min": 0, "max": 1},
            "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 12, "bottom": 2, "borderColor": "#334155", "fillerColor": "rgba(45,212,191,.24)"}],
            "legend": {"top": 0, "right": 0, "textStyle": {"color": "#94a3b8", "fontSize": 11}}, "series": series}


@ui.page("/")
def smartcut_page() -> None:
    ui.dark_mode().enable()
    ui.add_head_html("""<style>
body { background:#10161b; color:#e5e7eb; } .nicegui-content { padding-bottom:122px; }
.rc-card { background:#151d24; border:1px solid #2b3a47; border-radius:14px; box-shadow:none; }
.rc-muted { color:#94a3b8; } .rc-cut { border-left:3px solid #fb7185; background:#1a2530; border-radius:8px; }
.rc-cut-active { outline:1px solid #3b82f6; background:#202f3c; } .rc-chip { border:1px solid #2dd4bf; color:#2dd4bf; border-radius:999px; padding:3px 9px; font-size:11px; }
.rc-bottom { background:#111a21; border-top:1px solid #2b3a47; }
</style>""")
    state = {"files": [], "selected": None, "running": False, "active_cut": None}

    with ui.header().classes("items-center gap-3 px-5").style("height:70px;background:#151b21;border-bottom:1px solid #2b3a47"):
        ui.icon("content_cut", size="md").classes("text-teal-300 rounded p-2").style("background:#164e4a")
        ui.label("Remoção de silêncios").classes("text-base font-bold")
        ui.separator().props("vertical").classes("h-8")
        active_file = ui.label("Nenhum arquivo carregado").classes("text-sm rc-muted flex-grow")
        preset = ui.toggle(list_presets(), value="colab").props("dense no-caps").classes("text-sm")
        ui.badge("🛡 Nunca sobrescreve os originais", color="teal").props("outline")

    # Controls are created once so values survive a re-render of the side panel.
    base_rules = load_rules("colab")
    within = ui.slider(min=.25, max=2.5, step=.05, value=base_rules.pause_within_sentence_s).props("label-always color=teal")
    after = ui.slider(min=.2, max=2.5, step=.05, value=base_rules.pause_after_sentence_s).props("label-always color=teal")
    minimum = ui.slider(min=.15, max=2, step=.05, value=base_rules.min_segment_s).props("label-always color=teal")
    breath = ui.slider(min=0, max=.6, step=.05, value=base_rules.breath_padding_s).props("label-always color=teal")
    crossfade = ui.slider(min=0, max=120, step=5, value=base_rules.audio_crossfade_ms).props("label-always color=teal")
    protect = ui.switch("Proteger pausas dramáticas", value=True).props("color=teal")
    punch = ui.switch("Disfarce de jump cut", value=False).props("color=teal")

    with ui.column().classes("w-full gap-3 p-4"):
        with ui.row().classes("w-full items-end gap-2"):
            folder = ui.input("Pasta raw").classes("flex-grow")
            browse = ui.button(icon="folder_open").props("outline round")
            load = ui.button("Carregar vídeos", icon="video_library").props("no-caps outline")
            output = ui.input("Saída").classes("w-80")
        with ui.row().classes("w-full gap-3 items-stretch").style("flex-wrap:nowrap; min-height:640px"):
            with ui.card().classes("rc-card w-1/4 min-w-72 p-4"):
                ui.label("Regras de corte").classes("font-bold")
                ui.label("preset · ajuste fino antes de processar").classes("text-xs rc-muted")
                rules_box = ui.column().classes("w-full gap-3 mt-3")
                ui.separator().classes("my-1")
                ui.label("Áudio (opcional)").classes("font-bold text-sm")
                denoise = ui.checkbox("Denoise DeepFilterNet").classes("text-sm rc-muted"); denoise.disable()
                normalize = ui.checkbox("Normalizar para -14 LUFS", value=True).classes("text-sm")
                ui.separator()
                analyze = ui.button("Analisar selecionados", icon="graphic_eq", color="primary").props("no-caps").classes("w-full")
            with ui.card().classes("rc-card flex-grow min-w-0 p-4"):
                with ui.row().classes("w-full items-center"):
                    ui.label("Timeline de revisão").classes("font-bold flex-grow")
                    ui.label("■ corte proposto").classes("text-xs text-pink-400")
                    ui.label("■ mantido").classes("text-xs text-teal-300")
                    ui.label("■ pausa protegida").classes("text-xs text-amber-300")
                player_box = ui.column().classes("w-full")
                timeline_box = ui.column().classes("w-full")
                with ui.row().classes("w-full items-center mt-3"):
                    ui.label("CORTES PROPOSTOS").classes("text-xs font-bold rc-muted flex-grow")
                    cuts_count = ui.label("").classes("text-xs rc-muted")
                cuts_box = ui.column().classes("w-full gap-2")
                with ui.row().classes("w-full gap-3 mt-2"):
                    retakes_box = ui.column().classes("w-1/2")
                    protected_box = ui.column().classes("w-1/2")
                transcript_box = ui.column().classes("w-full mt-3")
            with ui.card().classes("rc-card w-1/4 min-w-72 p-4"):
                ui.label("Resultado").classes("font-bold")
                result_box = ui.column().classes("w-full gap-3 mt-3")
        with ui.card().classes("rc-card w-full p-3"):
            with ui.row().classes("w-full items-center"):
                ui.label("Arquivos brutos").classes("font-bold flex-grow")
                all_button = ui.button("Selecionar todos").props("flat dense no-caps")
                none_button = ui.button("Limpar").props("flat dense no-caps")
            files_box = ui.row().classes("w-full gap-2 mt-2").style("flex-wrap:wrap")
    with ui.footer().classes("rc-bottom items-center p-4 gap-3"):
        process = ui.button("▶ Processar selecionados", color="teal").props("no-caps").classes("font-bold")
        status = ui.label("Carregue uma pasta raw para começar.").classes("text-sm rc-muted flex-grow")
        ui.label("VAD em cache ✓").classes("rc-chip")
        progress = ui.linear_progress(value=0).classes("w-48"); progress.set_visibility(False)

    def item() -> dict | None:
        return next((entry for entry in state["files"] if entry["path"] == state["selected"]), None)

    def rules_from_controls() -> CutRules:
        return replace(load_rules(preset.value), pause_within_sentence_s=round(within.value, 2), pause_after_sentence_s=round(after.value, 2), breath_padding_s=round(breath.value, 2), min_segment_s=round(minimum.value, 2), audio_crossfade_ms=int(crossfade.value), preserve_dramatic_pauses=protect.value, punch_in=punch.value)

    def refresh_plan() -> None:
        current = item()
        if current and current.get("plan"):
            plan = current["plan"]
            plan.cuts = cuts_from_words(plan.words, rules_from_controls(), plan.protected_pauses if protect.value else [])
            state["active_cut"] = None; render_review()

    def render_rules() -> None:
        rules_box.clear(); rules = load_rules(preset.value)
        within.set_value(rules.pause_within_sentence_s); after.set_value(rules.pause_after_sentence_s)
        minimum.set_value(rules.min_segment_s); breath.set_value(rules.breath_padding_s); crossfade.set_value(rules.audio_crossfade_ms)
        protect.set_value(rules.preserve_dramatic_pauses); punch.set_value(rules.punch_in)
        with rules_box:
            for title, control, note in (("Pausa dentro da frase", within, "mantém respiro no diálogo"), ("Pausa após fim de frase", after, "preserva intenção editorial"), ("Trecho mínimo entre cortes", minimum, "abaixo disso os cortes se mesclam"), ("Respiro preservado", breath, "nunca corta no meio da palavra"), ("Crossfade de áudio", crossfade, "suaviza a emenda")):
                ui.label(title).classes("text-sm"); control.move(rules_box); ui.label(note).classes("text-xs rc-muted")
            protect.move(rules_box); punch.move(rules_box)

    def render_files() -> None:
        files_box.clear()
        with files_box:
            for entry in state["files"]:
                selected_class = "border border-blue-500" if entry["path"] == state["selected"] else ""
                with ui.card().classes(f"rc-card w-48 p-2 {selected_class}"):
                    image = ui.image(f"/media/{entry['thumb_key']}").classes("w-full rounded bg-black cursor-pointer"); image.style("height:96px;object-fit:cover")
                    image.on("click", lambda _, current=entry: select(current))
                    with ui.row().classes("w-full items-center no-wrap"):
                        check = ui.checkbox(value=entry["selected"]).props("dense")
                        check.on_value_change(lambda event, current=entry: current.update(selected=bool(event.value)))
                        ui.label(entry["name"]).classes("text-xs ellipsis flex-grow")
                    ui.label(_clock(entry["duration"], brief=True)).classes("text-xs rc-muted")
                    if entry.get("plan"): ui.badge(f"{len(entry['plan'].cuts)} cortes", color="teal").props("dense")

    def select(entry: dict) -> None:
        state["selected"] = entry["path"]; state["active_cut"] = None; active_file.text = entry["name"]
        render_files(); render_review()

    def toggle_cut(current: dict, index: int) -> None:
        disabled = current.setdefault("disabled_cuts", set())
        disabled.symmetric_difference_update({index}); render_review()

    def render_review() -> None:
        for box in (player_box, timeline_box, cuts_box, retakes_box, protected_box, transcript_box, result_box): box.clear()
        current = item()
        if not current or not current.get("plan"):
            with timeline_box: ui.label("Selecione um vídeo e execute a análise para montar a revisão.").classes("rc-muted text-sm p-12")
            return
        plan = current["plan"]; disabled = current.setdefault("disabled_cuts", set()); visible = [cut for index, cut in enumerate(plan.cuts) if index not in disabled]
        removed = sum(cut.end_s - cut.start_s for cut in visible); source_key = _key(current.get("rendered") or current["path"]); MEDIA[source_key] = current.get("rendered") or current["path"]
        with player_box: ui.video(f"/media/{source_key}").classes("w-full").style("max-height:220px;background:#000")
        with timeline_box: ui.echart(_timeline(plan, current["duration"], state["active_cut"])).classes("w-full").style("height:210px;background:#0d141a;border:1px solid #2b3a47;border-radius:10px")
        cuts_count.text = f"{len(visible)} ativos · {len(disabled)} mantidos"
        with cuts_box:
            for index, cut in enumerate(plan.cuts[:18]):
                kept, active = index in disabled, state["active_cut"] == index
                classes = "rc-cut w-full p-2" + (" opacity-50" if kept else "") + (" rc-cut-active" if active else "")
                with ui.row().classes(classes + " items-center no-wrap"):
                    ui.label(_clock(cut.start_s, brief=True)).classes("text-sm rc-muted w-14")
                    with ui.column().classes("flex-grow gap-0"):
                        ui.label("mantido" if kept else cut.reason.replace("_", " ")).classes("text-xs " + ("text-teal-300" if kept else "text-pink-400"))
                        ui.label(_context(plan, cut)).classes("text-xs rc-muted ellipsis")
                    ui.button(icon="visibility", on_click=lambda _, i=index: (state.update(active_cut=i), render_review())).props("flat dense round")
                    ui.button("Restaurar" if kept else "Remover", on_click=lambda _, i=index: toggle_cut(current, i)).props("dense no-caps").classes("text-xs").style("background:#2dd4bf;color:#111827" if kept else "background:#fb7185;color:#111827")
        with retakes_box:
            ui.label("RETAKES DETECTADOS").classes("text-xs font-bold rc-muted")
            ui.label("Nenhum retake automático." if not plan.retakes else str(plan.retakes[:3])).classes("text-xs rc-muted")
        with protected_box:
            ui.label("PAUSAS PROTEGIDAS").classes("text-xs font-bold rc-muted")
            ui.label("Nenhuma pausa marcada." if not plan.protected_pauses else " · ".join(f"{_clock(p.start_s, brief=True)}–{_clock(p.end_s, brief=True)}" for p in plan.protected_pauses[:3])).classes("text-xs rc-muted")
        with transcript_box:
            ui.label("TRANSCRIÇÃO SINCRONIZADA").classes("text-xs font-bold rc-muted")
            ui.label(" ".join(word.text for word in plan.words) or "A transcrição não trouxe palavras.").classes("text-sm leading-7")
        with result_box:
            with ui.card().classes("w-full p-3").style("background:#1b2731;border:1px solid #2b3a47"):
                ui.label(f"{_clock(current['duration'], brief=True)} → {_clock(current['duration'] - removed, brief=True)}").classes("text-xl font-bold text-teal-300")
                ui.label(f"−{100 * removed / current['duration']:.1f}% removido").classes("text-sm text-pink-400")
                ui.label(f"{len(visible)} cortes · {removed:.1f}s economizados").classes("text-sm mt-2")
            ui.label("SAÍDA").classes("text-xs font-bold rc-muted")
            for name, artifact in current["artifacts"].items(): ui.label(f"✓ {name.upper()} · {artifact.name}").classes("text-xs text-teal-300")
            if current.get("rendered"): ui.label(f"✓ MP4 · {Path(current['rendered']).name}").classes("text-xs text-teal-300")

    async def load_files() -> None:
        if not folder.value: ui.notify("Escolha a pasta raw primeiro.", type="warning"); return
        paths = await run.io_bound(list_videos, folder.value); result = []
        for path in paths:
            duration = await run.io_bound(probe_duration, path); thumb = THUMB_DIR / f"{_key(str(path))}.jpg"
            if not thumb.is_file(): await run.io_bound(extract_thumbnail, path, thumb, duration_s=duration)
            MEDIA[_key(str(thumb))] = str(thumb); result.append({"path": str(path), "name": path.name, "duration": duration, "selected": True, "thumb_key": _key(str(thumb))})
        state.update(files=result, selected=result[0]["path"] if result else None); output.value = str(default_output_dir(folder.value)); active_file.text = result[0]["name"] if result else "Nenhum vídeo encontrado"
        render_files(); render_review()

    async def analyze_selected() -> None:
        targets = [entry for entry in state["files"] if entry["selected"]]
        if not targets or state["running"]: return
        state["running"] = True; progress.set_visibility(True)
        try:
            for index, entry in enumerate(targets, 1):
                status.text = f"{index}/{len(targets)} · extraindo áudio, VAD e transcrição: {entry['name']}"; source = entry["path"]
                if normalize.value:
                    audio_dir = Path(output.value) / ".audio"; extracted = await run.io_bound(extract_audio, entry["path"], audio_dir / f"{Path(entry['path']).stem}.m4a")
                    source = await run.io_bound(normalize_loudness, extracted, audio_dir / f"{Path(entry['path']).stem}__lufs.m4a")
                plan, artifacts = await run.io_bound(analyze_clip, entry["path"], output.value, preset=preset.value, analysis_source=source)
                entry.update(plan=plan, artifacts=artifacts, disabled_cuts=set()); progress.value = index / len(targets); render_files()
                if entry["path"] == state["selected"]: render_review()
        finally:
            state["running"] = False; progress.set_visibility(False); status.text = "Análise concluída. Revise os cortes antes de processar."

    async def process_selected() -> None:
        targets = [entry for entry in state["files"] if entry["selected"] and entry.get("plan")]
        if not targets or state["running"]: ui.notify("Analise ao menos um vídeo antes de processar.", type="warning"); return
        state["running"] = True; progress.set_visibility(True)
        try:
            for index, entry in enumerate(targets, 1):
                status.text = f"{index}/{len(targets)} · renderizando: {entry['name']}"; disabled = entry.get("disabled_cuts", set())
                reviewed = replace(entry["plan"], cuts=[cut for i, cut in enumerate(entry["plan"].cuts) if i not in disabled])
                rendered, _ = await run.io_bound(render_with_handles, reviewed, output.value); entry["rendered"] = str(rendered); progress.value = index / len(targets)
                if entry["path"] == state["selected"]: render_review()
        finally:
            state["running"] = False; progress.set_visibility(False); status.text = f"Render concluído em {output.value}"

    async def browse_folder() -> None:
        chosen = await run.io_bound(choose_directory)
        if chosen: folder.value = chosen; await load_files()

    def set_all(value: bool) -> None:
        for entry in state["files"]: entry["selected"] = value
        render_files()

    for control in (within, after, minimum, breath, crossfade, protect, punch): control.on_value_change(lambda _: refresh_plan())
    preset.on_value_change(lambda _: (render_rules(), refresh_plan()))
    browse.on_click(browse_folder); load.on_click(load_files); analyze.on_click(analyze_selected); process.on_click(process_selected)
    all_button.on_click(lambda: set_all(True)); none_button.on_click(lambda: set_all(False)); render_rules()
