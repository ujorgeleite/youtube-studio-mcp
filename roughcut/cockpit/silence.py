"""Painel compacto para análise e remoção de silêncios."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from cockpit.filepicker import choose_directory
from silence.analyze import analyze_video, extract_thumbnail, list_videos, probe_duration
from silence.policy import MODES, complement, plan_for
from silence.render import default_output_dir, render_plan
from silence.schema import Interval, SilenceSettings

SOURCE_REGISTRY: dict[str, str] = {}
RESULT_REGISTRY: dict[str, str] = {}
THUMB_REGISTRY: dict[str, str] = {}
THUMB_DIR = Path(__file__).resolve().parents[1] / ".silence-cache" / "thumbnails"
STATUS = {
    "new": ("Não analisado", "grey"), "analyzing": ("Analisando", "blue"),
    "ready": ("Pronto", "green"), "no_gain": ("Sem ganho relevante", "grey"),
    "processing": ("Processando", "blue"), "done": ("Concluído", "green"),
    "error": ("Erro", "red"),
}


def _media_key(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:20]


@app.get("/silence-source/{key}")
def _serve_source(key: str):
    path = SOURCE_REGISTRY.get(key)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.get("/silence-result/{key}")
def _serve_result(key: str):
    path = RESULT_REGISTRY.get(key)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.get("/silence-thumbnail/{key}")
def _serve_thumbnail(key: str):
    path = THUMB_REGISTRY.get(key)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


def _clock(seconds: float) -> str:
    minutes, secs = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _removed(item: dict) -> tuple[float, float]:
    if not item.get("plan"):
        return 0.0, 0.0
    seconds = max(0.0, item["duration_s"] - item["plan"]["estimated_output_duration_s"])
    return seconds, 100 * seconds / item["duration_s"] if item["duration_s"] else 0.0


def _waveform_options(analysis, plan: dict) -> dict:
    points = [[round(i * analysis.duration_s / max(1, len(analysis.waveform) - 1), 3), value]
              for i, value in enumerate(analysis.waveform)]
    keeps = [Interval(float(part["start_s"]), float(part["end_s"])) for part in plan["keep"]]
    return {
        "animation": False, "grid": {"left": 45, "right": 20, "top": 20, "bottom": 40},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "value", "name": "segundos", "min": 0, "max": round(analysis.duration_s, 2)},
        "yAxis": {"type": "value", "min": 0, "max": 1, "show": False},
        "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 16}],
        "series": [{"type": "line", "data": points, "symbol": "none",
                    "lineStyle": {"width": 1, "color": "#60a5fa"},
                    "areaStyle": {"color": "rgba(59,130,246,.28)"},
                    "markArea": {"silent": True, "itemStyle": {"color": "rgba(239,68,68,.30)"},
                                 "data": [[{"xAxis": part.start_s}, {"xAxis": part.end_s}]
                                          for part in complement(analysis.duration_s, keeps)]}}],
    }


@ui.page("/silence")
def silence_page() -> None:
    ui.dark_mode().enable()
    state: dict = {"files": [], "selected": None, "running": False}

    with ui.header().classes("items-center gap-3"):
        ui.label("roughcut — cockpit").classes("text-lg font-bold")
        ui.link("Pré-montagem", "/").classes("text-sm text-white")
        ui.link("Remover silêncios", "/silence").classes("text-sm text-amber-300 font-bold")
        ui.space(); ui.label("originais preservados").classes("text-xs opacity-70")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-3"):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-end gap-2"):
                folder = ui.input("Pasta raw").classes("flex-grow")
                browse = ui.button(icon="folder_open").props("outline")
                load_button = ui.button("Carregar vídeos", icon="refresh")
            output_dir = ui.input("Resultados em nova pasta").classes("w-full")

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center gap-3"):
                summary = ui.label("Carregue uma pasta para começar").classes("text-sm font-medium flex-grow")
                use_proxy = ui.checkbox("Usar proxy LRF", value=True)
                analysis_parallel = ui.select([1, 2, 3, 4], value=2, label="Análises simultâneas").classes("w-44")
                render_parallel = ui.select([1, 2, 3, 4], value=2, label="Renders simultâneos").classes("w-44")
            with ui.row().classes("w-full items-end gap-3"):
                min_removed_s = ui.number("Remoção mínima (s)", value=1.0, step=0.1).classes("w-44")
                min_removed_pct = ui.number("Remoção mínima (%)", value=0.25, step=0.05).classes("w-44")
                always_render = ui.checkbox("Sempre renderizar", value=False)
                analyze_button = ui.button("Analisar selecionados", icon="graphic_eq", color="primary")
                process_button = ui.button("Processar selecionados", icon="content_cut", color="green")
            progress = ui.linear_progress(value=0).classes("w-full"); progress.set_visibility(False)
            progress_label = ui.label("").classes("text-xs opacity-70")

        with ui.row().classes("w-full gap-3 items-start").style("flex-wrap:nowrap"):
            with ui.card().classes("w-5/12 min-w-96"):
                with ui.row().classes("w-full items-center gap-1"):
                    ui.label("Vídeos").classes("font-bold flex-grow")
                    select_all = ui.button("Todos").props("flat dense")
                    select_none = ui.button("Nenhum").props("flat dense")
                    invert = ui.button("Inverter").props("flat dense")
                search = ui.input(placeholder="Buscar arquivo…").props("dense clearable").classes("w-full")
                filter_toggle = ui.toggle({"all": "Todos", "review": "Revisar", "ready": "Prontos", "done": "Feitos"}, value="all").classes("w-full")
                files_box = ui.column().classes("w-full gap-1").style("max-height:68vh;overflow-y:auto")
            with ui.card().classes("flex-grow min-w-0"):
                inspector = ui.column().classes("w-full")

    with ui.footer().classes("items-center gap-3 px-5"):
        batch_status = ui.label("Nenhum vídeo selecionado").classes("text-sm flex-grow")
        ui.button("Analisar", icon="graphic_eq", on_click=lambda: _analyze_selected()).props("outline")
        ui.button("Processar", icon="content_cut", color="green", on_click=lambda: _process_selected())

    def _selected() -> list[dict]: return [item for item in state["files"] if item["selected"]]

    def _visible() -> list[dict]:
        needle = (search.value or "").lower(); selected_filter = filter_toggle.value
        allowed = {"review": {"new", "error", "no_gain"}, "ready": {"ready"}, "done": {"done"}}
        return [item for item in state["files"] if (not needle or needle in item["name"].lower())
                and (selected_filter == "all" or item["status"] in allowed[selected_filter])]

    def _refresh_summary() -> None:
        files, selected = state["files"], _selected()
        duration = sum(item["duration_s"] for item in selected); removable = sum(_removed(item)[0] for item in selected)
        ready = sum(item["status"] == "ready" for item in files); review = sum(item["status"] in {"new", "no_gain", "error"} for item in files)
        summary.text = f"{len(files)} vídeos · {len(selected)} selecionados · {_clock(duration)} · {_clock(removable)} removíveis · {ready} prontos · {review} para revisar"
        batch_status.text = f"{len(selected)} selecionados · {_clock(removable)} potencialmente removíveis"

    def _select_item(item: dict) -> None:
        state["selected"] = item["path"]; _render_list(); _render_inspector()

    def _render_list() -> None:
        files_box.clear()
        with files_box:
            for item in _visible():
                label, color = STATUS[item["status"]]; removed_s, removed_pct = _removed(item)
                with ui.card().classes("w-full p-2 gap-1 " + ("bg-blue-950" if item["path"] == state["selected"] else "")):
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        check = ui.checkbox(value=item["selected"]).props("dense")
                        check.on_value_change(lambda e, current=item: _set_checked(current, e.value))
                        image = ui.image(f"/silence-thumbnail/{item['key']}").classes("rounded bg-black")
                        image.style("width:72px;height:42px;object-fit:cover;cursor:pointer"); image.on("click", lambda _, current=item: _select_item(current))
                        with ui.column().classes("gap-0 flex-grow"):
                            name = ui.label(item["name"]).classes("text-xs font-medium truncate"); name.on("click", lambda _, current=item: _select_item(current))
                            ui.label(_clock(item["duration_s"])).classes("text-xs opacity-60")
                        ui.badge(label, color=color).classes("text-xs")
                    if item.get("plan"):
                        ui.label(f"remove {_clock(removed_s)} · {removed_pct:.1f}% · {len(item['plan']['dialogues'])} blocos").classes("text-xs text-amber-300 ml-9")
                    if item["status"] == "processing":
                        ui.linear_progress(value=item.get("render_progress", 0)).classes("w-full")
                        ui.label(item.get("detail", "Preparando…")).classes("text-xs opacity-70")
        _refresh_summary()

    def _render_inspector() -> None:
        inspector.clear(); item = next((x for x in state["files"] if x["path"] == state["selected"]), None)
        with inspector:
            if item is None:
                ui.label("Selecione um vídeo para inspecionar").classes("text-sm opacity-60 p-8"); return
            ui.label(item["name"]).classes("text-lg font-bold break-all")
            if not item.get("analysis"):
                ui.label("Ainda não analisado.").classes("text-sm opacity-60"); return
            analysis, plan = item["analysis"], item["plan"]; removed_s, removed_pct = _removed(item)
            ui.label(f"{_clock(item['duration_s'])} → {_clock(plan['estimated_output_duration_s'])} · remove {_clock(removed_s)} ({removed_pct:.1f}%)").classes("text-sm text-amber-300")
            if item["status"] == "no_gain":
                ui.label("Recomendação: copiar sem reencodar; a remoção está abaixo do limite configurado.").classes("text-xs text-blue-300")
            elif item["status"] in {"ready", "done"}:
                ui.label("Recomendação: processar; há remoção relevante neste vídeo.").classes("text-xs text-green-300")
            source_note = "⚡ análise com proxy DJI LRF; render com MP4 original" if analysis.analysis_source_kind == "dji_lrf_proxy" else "análise com MP4 original"
            ui.label(source_note).classes("text-xs opacity-70")
            video_path, route = (item["output"], "silence-result") if item.get("output") else (item["path"], "silence-source")
            registry = RESULT_REGISTRY if item.get("output") else SOURCE_REGISTRY; key = _media_key(video_path); registry[key] = video_path
            ui.video(f"/{route}/{key}").classes("w-full max-w-3xl")
            mode = ui.toggle(MODES, value=item["mode"]).classes("w-full"); mode.on_value_change(lambda e, current=item: _set_mode(current, e.value))
            ui.echart(_waveform_options(analysis, plan)).classes("w-full h-64")
            with ui.expansion("Ajuste fino dos trechos mantidos", icon="tune").classes("w-full"):
                rows = []
                for index, keep in enumerate(plan["keep"], 1):
                    row = {"enabled": True}
                    with ui.row().classes("w-full items-center gap-2"):
                        enabled = ui.checkbox(f"{index}", value=True); enabled.on_value_change(lambda e, current=row: current.update(enabled=e.value))
                        row["start"] = ui.number("Início", value=keep["start_s"], step=0.01).classes("w-32")
                        row["end"] = ui.number("Fim", value=keep["end_s"], step=0.01).classes("w-32")
                    rows.append(row)
                ui.button("Aplicar ajustes", on_click=lambda current=item, current_rows=rows: _apply_edits(current, current_rows)).props("outline")
            if plan.get("render"): ui.label(f"Resultado: {plan['render']['strategy']}").classes("text-xs text-green-300")

    def _set_checked(item: dict, value: bool) -> None: item["selected"] = bool(value); _render_list()

    def _apply_render_options(item: dict) -> None:
        item["plan"]["render_options"] = {"min_removed_s": float(min_removed_s.value), "min_removed_pct": float(min_removed_pct.value), "always_render": bool(always_render.value)}

    def _set_status_from_plan(item: dict) -> None:
        removed_s, removed_pct = _removed(item); opts = item["plan"]["render_options"]
        item["status"] = "no_gain" if not opts["always_render"] and (removed_s < opts["min_removed_s"] or removed_pct < opts["min_removed_pct"]) else "ready"

    def _make_plan(item: dict) -> None:
        item["plan"] = plan_for(item["analysis"], item["mode"]); _apply_render_options(item); _set_status_from_plan(item)

    def _set_mode(item: dict, mode: str) -> None: item["mode"] = mode; _make_plan(item); _render_list(); _render_inspector()

    def _apply_edits(item: dict, rows: list[dict]) -> None:
        keeps = [Interval(float(row["start"].value), float(row["end"].value)) for row in rows if row["enabled"] and row["end"].value > row["start"].value]
        item["plan"] = plan_for(item["analysis"], item["mode"], keeps=keeps); _apply_render_options(item); _set_status_from_plan(item); _render_list(); _render_inspector()

    def _set_selection(value: bool | None) -> None:
        for item in state["files"]: item["selected"] = not item["selected"] if value is None else value
        _render_list()

    async def _choose_folder() -> None:
        chosen = await run.io_bound(choose_directory, "Selecione a pasta raw de vídeos")
        if chosen: folder.value = chosen; await _load_files()

    async def _load_files() -> None:
        if not folder.value: ui.notify("Escolha a pasta raw", type="warning"); return
        load_button.disable()
        try:
            paths = await run.io_bound(list_videos, folder.value); files = []
            for path in paths:
                duration = await run.io_bound(probe_duration, path); key = _media_key(str(path)); SOURCE_REGISTRY[key] = str(path); thumb = THUMB_DIR / f"{key}.jpg"
                if not thumb.is_file(): await run.io_bound(extract_thumbnail, path, thumb, duration_s=duration)
                THUMB_REGISTRY[key] = str(thumb)
                files.append({"path": str(path), "name": path.name, "duration_s": duration, "key": key, "selected": True, "status": "new", "mode": "around_dialogues"})
            state.update(files=files, selected=files[0]["path"] if files else None); output_dir.value = str(default_output_dir(folder.value)); _render_list(); _render_inspector()
        except Exception as exc: ui.notify(f"Não foi possível carregar: {exc}", type="negative", multi_line=True)
        finally: load_button.enable()

    async def _analyze_selected() -> None:
        targets = _selected()
        if not targets or state["running"]: return
        state["running"] = True; analyze_button.disable(); progress.set_visibility(True); settings = SilenceSettings(); semaphore = asyncio.Semaphore(int(analysis_parallel.value)); completed = 0
        async def _one(item: dict) -> None:
            nonlocal completed
            async with semaphore:
                item.update(status="analyzing", detail="Lendo áudio…")
                try:
                    item["analysis"] = await run.io_bound(analyze_video, item["path"], settings, use_lrf_proxy=bool(use_proxy.value)); _make_plan(item)
                except Exception as exc: item.update(status="error", detail=str(exc))
                completed += 1; progress.value = completed / len(targets); progress_label.text = f"Analisados {completed}/{len(targets)}"; _render_list()
                if item["path"] == state["selected"]: _render_inspector()
        try: await asyncio.gather(*(_one(item) for item in targets))
        finally: state["running"] = False; analyze_button.enable(); progress.set_visibility(False); _render_list()

    async def _process_selected() -> None:
        targets = [item for item in _selected() if item.get("plan") and item["status"] in {"ready", "no_gain"}]
        if not targets or state["running"]: ui.notify("Selecione vídeos analisados", type="warning"); return
        state["running"] = True; process_button.disable(); progress.set_visibility(True); semaphore = asyncio.Semaphore(int(render_parallel.value)); completed = 0
        async def _one(item: dict) -> None:
            nonlocal completed
            async with semaphore:
                item.update(status="processing", render_progress=0.0, detail="Preparando…")
                def _on_progress(done: int, total: int) -> None: item.update(render_progress=done / max(1, total), detail="Finalizando MP4…" if done >= total else f"Renderizando {done}/{total}")
                try:
                    output, _ = await run.io_bound(render_plan, item["plan"], output_dir.value, _on_progress); item.update(status="done", output=str(output), render_progress=1.0, detail="Concluído"); RESULT_REGISTRY[_media_key(str(output))] = str(output)
                except Exception as exc: item.update(status="error", detail=str(exc))
                completed += 1; progress.value = completed / len(targets); progress_label.text = f"Concluídos {completed}/{len(targets)}"; _render_list()
                if item["path"] == state["selected"]: _render_inspector()
        try:
            await asyncio.gather(*(_one(item) for item in targets)); ui.notify(f"Resultados em {Path(output_dir.value).resolve()}", type="positive", multi_line=True)
        finally: state["running"] = False; process_button.enable(); progress.set_visibility(False); _render_list()

    browse.on_click(_choose_folder); load_button.on_click(_load_files); select_all.on_click(lambda: _set_selection(True)); select_none.on_click(lambda: _set_selection(False)); invert.on_click(lambda: _set_selection(None)); search.on_value_change(lambda _: _render_list()); filter_toggle.on_value_change(lambda _: _render_list()); analyze_button.on_click(_analyze_selected); process_button.on_click(_process_selected)
