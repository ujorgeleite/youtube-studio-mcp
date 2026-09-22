from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from silence.analyze import extract_thumbnail, list_videos, probe_duration
from smartcut.config import list_presets, load_rules
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


def _clock(seconds: float) -> str:
    minutes, secs = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _timeline(words, cuts, duration: float) -> dict:
    data = [[word.start_s, max(.04, word.end_s-word.start_s)] for word in words]
    return {
        "animation": False, "grid": {"left": 35, "right": 20, "top": 20, "bottom": 35},
        "xAxis": {"type": "value", "min": 0, "max": duration},
        "yAxis": {"show": False}, "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16}],
        "series": [{"type": "bar", "data": data, "barWidth": 4, "itemStyle": {"color": "#2dd4bf"},
                    "markArea": {"itemStyle": {"color": "rgba(251,113,133,.4)"},
                                 "data": [[{"xAxis": cut.start_s}, {"xAxis": cut.end_s}] for cut in cuts]}}],
    }


@ui.page("/")
def smartcut_page() -> None:
    ui.dark_mode().enable()
    state = {"files": [], "selected": None, "running": False}

    with ui.header().classes("items-center gap-3"):
        ui.icon("content_cut", size="sm").classes("text-teal-300")
        ui.label("Remoção de silêncios").classes("text-lg font-bold")
        ui.space()
        ui.badge("Nunca sobrescreve os originais", color="teal")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-3"):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-end gap-2"):
                folder = ui.input("Pasta raw").classes("flex-grow")
                browse = ui.button(icon="folder_open").props("outline")
                load = ui.button("Carregar vídeos")
                preset = ui.select(list_presets(), value="colab", label="Preset").classes("w-44")
            output = ui.input("Pasta de saída").classes("w-full")

        with ui.row().classes("w-full gap-3 items-start").style("flex-wrap:nowrap"):
            with ui.card().classes("w-1/4 min-w-72"):
                ui.label("Regras de corte").classes("font-bold")
                rules_box = ui.column().classes("w-full gap-2")
                ui.separator()
                ui.label("Áudio opcional").classes("font-bold")
                denoise = ui.checkbox("Denoise DeepFilterNet (requer Rust)", value=False)
                denoise.disable()
                normalize = ui.checkbox("Normalizar para -14 LUFS", value=True)
                analyze = ui.button("Extrair e analisar", icon="graphic_eq", color="primary").classes("w-full")
                process = ui.button("Processar selecionados", icon="play_arrow", color="teal").classes("w-full")

            with ui.card().classes("flex-grow min-w-0"):
                ui.label("Timeline de revisão").classes("font-bold")
                timeline_box = ui.column().classes("w-full")
                cuts_box = ui.column().classes("w-full gap-2")

            with ui.card().classes("w-1/4 min-w-72"):
                ui.label("Resultado").classes("font-bold")
                result_box = ui.column().classes("w-full gap-3")

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center"):
                ui.label("Arquivos").classes("font-bold flex-grow")
                all_button = ui.button("Todos").props("flat dense")
                none_button = ui.button("Nenhum").props("flat dense")
            files_box = ui.row().classes("w-full gap-2").style("flex-wrap:wrap")
        status = ui.label("").classes("text-sm opacity-70")
        progress = ui.linear_progress(value=0).classes("w-full"); progress.set_visibility(False)

    def _render_rules() -> None:
        rules_box.clear(); rules = load_rules(preset.value)
        with rules_box:
            ui.label(f"Pausa dentro da frase: > {rules.pause_within_sentence_s}s").classes("text-sm")
            ui.label(f"Pausa após frase: mantém {rules.pause_after_sentence_s}s").classes("text-sm")
            ui.label(f"Respiro: {rules.breath_padding_s}s · trecho mínimo: {rules.min_segment_s}s").classes("text-xs opacity-70")
            ui.label(f"Crossfade: {rules.audio_crossfade_ms}ms").classes("text-xs opacity-70")

    def _render_files() -> None:
        files_box.clear()
        with files_box:
            for item in state["files"]:
                with ui.card().classes("w-48 p-2 " + ("bg-blue-950" if item["path"] == state["selected"] else "")):
                    image = ui.image(f"/media/{item['thumb_key']}").classes("w-full rounded bg-black")
                    image.style("height:96px;object-fit:cover"); image.on("click", lambda _, current=item: _select(current))
                    check = ui.checkbox(item["name"], value=item["selected"]).classes("text-xs break-all")
                    check.on_value_change(lambda event, current=item: current.update(selected=bool(event.value)))
                    ui.label(_clock(item["duration"])).classes("text-xs opacity-60")
                    if item.get("plan"):
                        ui.badge(f"{len(item['plan'].cuts)} cortes", color="teal")

    def _select(item: dict) -> None:
        state["selected"] = item["path"]; _render_files(); _render_review()

    def _render_review() -> None:
        timeline_box.clear(); cuts_box.clear(); result_box.clear()
        item = next((entry for entry in state["files"] if entry["path"] == state["selected"]), None)
        with timeline_box:
            if not item or not item.get("plan"):
                ui.label("Selecione um vídeo e rode a análise.").classes("text-sm opacity-60 p-8"); return
            plan = item["plan"]; key = _key(item.get("rendered") or item["path"]); MEDIA[key] = item.get("rendered") or item["path"]
            ui.video(f"/media/{key}").classes("w-full max-w-3xl")
            ui.echart(_timeline(plan.words, plan.cuts, plan.duration_s)).classes("w-full h-56")
        with cuts_box:
            ui.label("Cortes propostos").classes("font-bold text-sm")
            for cut in item["plan"].cuts[:12]:
                with ui.row().classes("w-full items-center"):
                    ui.label(f"{_clock(cut.start_s)} · {cut.reason}").classes("text-xs flex-grow")
                    ui.label(f"{cut.transcript_before} → {cut.transcript_after}").classes("text-xs opacity-70")
        with result_box:
            removed = sum(cut.end_s-cut.start_s for cut in item["plan"].cuts)
            ui.label(f"{_clock(item['duration'])} → {_clock(item['duration']-removed)}").classes("text-xl font-bold text-teal-300")
            ui.label(f"{len(item['plan'].cuts)} cortes · {len(item['plan'].retakes)} retakes").classes("text-sm")
            for name, artifact in item["artifacts"].items():
                ui.label(f"✓ {name}: {artifact.name}").classes("text-xs text-teal-300")
            if item.get("rendered"):
                ui.label(f"✓ MP4: {Path(item['rendered']).name}").classes("text-xs text-teal-300")

    async def _load() -> None:
        if not folder.value: return
        paths = await run.io_bound(list_videos, folder.value); result = []
        for path in paths:
            duration = await run.io_bound(probe_duration, path); thumb = THUMB_DIR / f"{_key(str(path))}.jpg"
            if not thumb.is_file(): await run.io_bound(extract_thumbnail, path, thumb, duration_s=duration)
            MEDIA[_key(str(thumb))] = str(thumb)
            result.append({"path": str(path), "name": path.name, "duration": duration, "selected": True, "thumb_key": _key(str(thumb))})
        state.update(files=result, selected=result[0]["path"] if result else None); output.value = str(default_output_dir(folder.value)); _render_files(); _render_review()

    async def _analyze() -> None:
        targets = [item for item in state["files"] if item["selected"]]
        if not targets or state["running"]: return
        state["running"] = True; progress.set_visibility(True)
        try:
            for index, item in enumerate(targets, 1):
                status.text = f"VAD + Whisper MLX {index}/{len(targets)}: {item['name']}"
                analysis_source = item["path"]
                if normalize.value:
                    audio_dir = Path(output.value) / ".audio"
                    extracted = await run.io_bound(extract_audio, item["path"], audio_dir / f"{Path(item['path']).stem}.m4a")
                    analysis_source = await run.io_bound(normalize_loudness, extracted, audio_dir / f"{Path(item['path']).stem}__lufs.m4a")
                plan, artifacts = await run.io_bound(analyze_clip, item["path"], output.value, preset=preset.value, analysis_source=analysis_source)
                item.update(plan=plan, artifacts=artifacts); progress.value = index / len(targets); _render_files()
                if item["path"] == state["selected"]: _render_review()
        finally:
            state["running"] = False; progress.set_visibility(False); status.text = "Análise concluída"

    async def _process() -> None:
        targets = [item for item in state["files"] if item["selected"] and item.get("plan")]
        if not targets or state["running"]: return
        state["running"] = True; progress.set_visibility(True)
        try:
            for index, item in enumerate(targets, 1):
                status.text = f"Renderizando {index}/{len(targets)}: {item['name']}"
                rendered, _ = await run.io_bound(render_with_handles, item["plan"], output.value)
                item["rendered"] = str(rendered); progress.value = index / len(targets)
                if item["path"] == state["selected"]: _render_review()
        finally:
            state["running"] = False; progress.set_visibility(False); status.text = f"Resultados em {output.value}"

    async def _browse() -> None:
        chosen = await run.io_bound(choose_directory)
        if chosen: folder.value = chosen; await _load()

    def _set_all(value: bool) -> None:
        for item in state["files"]: item["selected"] = value
        _render_files()

    preset.on_value_change(lambda _: _render_rules())
    browse.on_click(_browse); load.on_click(_load); analyze.on_click(_analyze); process.on_click(_process)
    all_button.on_click(lambda: _set_all(True)); none_button.on_click(lambda: _set_all(False)); _render_rules()
