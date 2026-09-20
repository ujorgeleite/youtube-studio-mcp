"""Tela de análise e remoção de silêncios do Cockpit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from cockpit.filepicker import choose_directory
from silence.analyze import analyze_video, list_videos, probe_duration
from silence.policy import MODES, complement, plan_for
from silence.render import default_output_dir, render_plan
from silence.schema import Interval, SilenceSettings

SOURCE_REGISTRY: dict[str, str] = {}
RESULT_REGISTRY: dict[str, str] = {}


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


def _clock(seconds: float) -> str:
    minutes, secs = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _waveform_options(analysis, plan: dict) -> dict:
    waveform = analysis.waveform
    duration = analysis.duration_s
    points = [
        [round(index * duration / max(1, len(waveform) - 1), 3), value]
        for index, value in enumerate(waveform)
    ]
    keeps = [Interval(float(item["start_s"]), float(item["end_s"])) for item in plan["keep"]]
    removals = complement(duration, keeps)
    return {
        "animation": False,
        "grid": {"left": 45, "right": 20, "top": 20, "bottom": 45},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "value", "name": "segundos", "min": 0, "max": round(duration, 2)},
        "yAxis": {"type": "value", "min": 0, "max": 1, "show": False},
        "dataZoom": [{"type": "inside"}, {"type": "slider", "height": 18}],
        "series": [
            {
                "type": "line",
                "data": points,
                "symbol": "none",
                "lineStyle": {"width": 1, "color": "#60a5fa"},
                "areaStyle": {"color": "rgba(59,130,246,.28)"},
                "markArea": {
                    "silent": True,
                    "itemStyle": {"color": "rgba(239,68,68,.30)"},
                    "data": [
                        [{"xAxis": item.start_s}, {"xAxis": item.end_s}]
                        for item in removals
                    ],
                },
            }
        ],
    }


@ui.page("/silence")
def silence_page() -> None:
    ui.dark_mode().enable()
    state: dict = {"files": [], "analyses": {}}

    with ui.header().classes("items-center gap-3"):
        ui.label("roughcut — cockpit").classes("text-lg font-bold")
        ui.link("Pré-montagem", "/").classes("text-sm text-white")
        ui.link("Remover silêncios", "/silence").classes("text-sm text-amber-300 font-bold")
        ui.space()
        ui.label("originais preservados").classes("text-xs opacity-70")

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("Remover silêncios").classes("text-2xl font-bold")
        ui.label(
            "Detecta múltiplos blocos de diálogo em cada vídeo. O resultado é gravado "
            "em uma nova pasta identificada como remocao-de-silencios; nenhum arquivo raw é alterado."
        ).classes("text-sm opacity-75")

        with ui.card().classes("w-full"):
            ui.label("1. Escolha a pasta raw").classes("font-bold")
            with ui.row().classes("w-full items-end gap-2"):
                folder = ui.input("Pasta com os vídeos raw").classes("flex-grow")
                browse = ui.button(icon="folder_open").props("outline")
                load_button = ui.button("Carregar vídeos", icon="refresh")
            output_dir = ui.input("Nova pasta de saída").classes("w-full")
            ui.label(
                "A pasta de saída é irmã da pasta raw e recebe o sufixo "
                "__remocao-de-silencios_DATA."
            ).classes("text-xs text-amber-300")

        files_card = ui.card().classes("w-full")
        files_card.set_visibility(False)
        with files_card:
            with ui.row().classes("w-full items-center"):
                ui.label("2. Selecione os vídeos").classes("font-bold")
                ui.space()
                select_all = ui.button("Selecionar todos").props("flat dense")
                select_none = ui.button("Desmarcar todos").props("flat dense")
                invert = ui.button("Inverter").props("flat dense")
            files_box = ui.column().classes("w-full gap-1")

        settings_card = ui.card().classes("w-full")
        settings_card.set_visibility(False)
        with settings_card:
            ui.label("3. Analisar os diálogos").classes("font-bold")
            with ui.row().classes("w-full gap-3"):
                noise = ui.number("Limite de silêncio (dB)", value=-35, step=1).classes("w-44")
                min_silence = ui.number("Silêncio mínimo (s)", value=0.35, step=0.05).classes("w-44")
                merge_gap = ui.number("Unir falas separadas por até (s)", value=2.5, step=0.1).classes("w-56")
                padding_before = ui.number("Margem antes (s)", value=0.08, step=0.01).classes("w-40")
                padding_after = ui.number("Margem depois (s)", value=0.15, step=0.01).classes("w-40")
            analyze_button = ui.button("Analisar selecionados", icon="graphic_eq").classes("w-full")
            analysis_status = ui.label("").classes("text-sm opacity-70")
            analysis_progress = ui.linear_progress(value=0).classes("w-full")
            analysis_progress.set_visibility(False)

        results_box = ui.column().classes("w-full gap-4")
        process_card = ui.card().classes("w-full")
        process_card.set_visibility(False)
        with process_card:
            ui.label("4. Processar vídeos analisados").classes("font-bold")
            ui.label(
                "Cada vídeo gera um MP4 __sem-silencios e um JSON com o plano aplicado."
            ).classes("text-sm opacity-70")
            process_button = ui.button("Processar selecionados", icon="content_cut", color="green").classes("w-full")
            process_status = ui.label("").classes("text-sm")
            process_progress = ui.linear_progress(value=0).classes("w-full")
            process_progress.set_visibility(False)
            processed_box = ui.column().classes("w-full")

    def _selected_files() -> list[dict]:
        return [item for item in state["files"] if item["selected"]]

    def _render_file_list() -> None:
        files_box.clear()
        with files_box:
            for item in state["files"]:
                with ui.row().classes("w-full items-center gap-2"):
                    checkbox = ui.checkbox(value=item["selected"])
                    checkbox.on_value_change(
                        lambda event, current=item: current.update(selected=bool(event.value))
                    )
                    ui.label(item["name"]).classes("flex-grow")
                    ui.label(_clock(item["duration_s"])).classes("text-xs opacity-60")

    def _set_selection(value: bool | None) -> None:
        for item in state["files"]:
            item["selected"] = not item["selected"] if value is None else value
        _render_file_list()

    async def _choose_folder() -> None:
        chosen = await run.io_bound(choose_directory, "Selecione a pasta raw de vídeos")
        if chosen:
            folder.value = chosen
            await _load_files()

    async def _load_files() -> None:
        if not folder.value:
            ui.notify("Escolha a pasta raw", type="warning")
            return
        try:
            paths = await run.io_bound(list_videos, folder.value)
            files = []
            for path in paths:
                duration = await run.io_bound(probe_duration, path)
                key = _media_key(str(path))
                SOURCE_REGISTRY[key] = str(path)
                files.append(
                    {"path": str(path), "name": path.name, "duration_s": duration, "selected": True, "key": key}
                )
        except Exception as exc:
            ui.notify(f"Não foi possível carregar a pasta: {exc}", type="negative", multi_line=True)
            return
        state["files"] = files
        state["analyses"] = {}
        output_dir.value = str(default_output_dir(folder.value))
        _render_file_list()
        files_card.set_visibility(True)
        settings_card.set_visibility(True)
        process_card.set_visibility(False)
        results_box.clear()
        if not files:
            ui.notify("Nenhum vídeo compatível encontrado", type="warning")

    def _rebuild_plan(entry: dict, mode: str | None = None) -> None:
        if mode:
            entry["mode"] = mode
        entry["plan"] = plan_for(entry["analysis"], entry["mode"])
        _render_results()

    def _apply_interval_edits(entry: dict, rows: list[dict]) -> None:
        keeps = []
        for row in rows:
            if row["selected"] and row["end"].value > row["start"].value:
                keeps.append(
                    Interval(float(row["start"].value), float(row["end"].value))
                )
        entry["plan"] = plan_for(entry["analysis"], entry["mode"], keeps=keeps)
        _render_results()

    def _render_results() -> None:
        results_box.clear()
        with results_box:
            for path, entry in state["analyses"].items():
                analysis = entry["analysis"]
                plan = entry["plan"]
                removed = analysis.duration_s - plan["estimated_output_duration_s"]
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center"):
                        ui.label(Path(path).name).classes("text-lg font-bold")
                        ui.space()
                        ui.label(
                            f"original {_clock(analysis.duration_s)} · saída estimada "
                            f"{_clock(plan['estimated_output_duration_s'])} · remove {_clock(removed)}"
                        ).classes("text-xs text-amber-300")
                    ui.video(f"/silence-source/{_media_key(path)}").classes("w-full max-w-2xl")
                    ui.label("Política de remoção").classes("text-sm font-medium")
                    mode_select = ui.toggle(MODES, value=entry["mode"]).classes("w-full")
                    mode_select.on_value_change(
                        lambda event, current=entry: _rebuild_plan(current, event.value)
                    )
                    ui.label(
                        "Azul = áudio. Vermelho = intervalo que será removido. Use o zoom sob o gráfico."
                    ).classes("text-xs opacity-70")
                    ui.echart(_waveform_options(analysis, plan)).classes("w-full h-64")
                    rows = []
                    with ui.expansion("Ajuste fino dos trechos mantidos", icon="tune").classes("w-full"):
                        ui.label(
                            "Cada linha é um trecho que permanecerá no vídeo final. Desmarque, "
                            "ou ajuste o início e o fim em segundos."
                        ).classes("text-xs opacity-70")
                        for index, keep in enumerate(plan["keep"], 1):
                            row = {"selected": True}
                            with ui.row().classes("w-full items-center gap-2"):
                                checkbox = ui.checkbox(f"Trecho {index}", value=True)
                                checkbox.on_value_change(
                                    lambda event, current=row: current.update(selected=bool(event.value))
                                )
                                row["start"] = ui.number("Início (s)", value=keep["start_s"], step=0.01).classes("w-36")
                                row["end"] = ui.number("Fim (s)", value=keep["end_s"], step=0.01).classes("w-36")
                                ui.label(f"{_clock(keep['start_s'])} → {_clock(keep['end_s'])}").classes("text-xs opacity-60")
                            rows.append(row)
                        ui.button(
                            "Aplicar ajustes ao gráfico",
                            icon="done",
                            on_click=lambda current=entry, current_rows=rows: _apply_interval_edits(current, current_rows),
                        ).props("outline")
                    ui.label(
                        f"{len(plan['dialogues'])} bloco(s) de diálogo detectado(s) · "
                        f"{len(analysis.silences)} silêncio(s) acústico(s)"
                    ).classes("text-xs opacity-60")
        process_card.set_visibility(bool(state["analyses"]))

    async def _analyze_selected() -> None:
        selected = _selected_files()
        if not selected:
            ui.notify("Selecione pelo menos um vídeo", type="warning")
            return
        settings = SilenceSettings(
            noise_db=float(noise.value),
            min_silence_s=float(min_silence.value),
            padding_before_s=float(padding_before.value),
            padding_after_s=float(padding_after.value),
            dialogue_merge_gap_s=float(merge_gap.value),
        )
        analyze_button.disable()
        analysis_progress.set_visibility(True)
        analysis_progress.value = 0
        state["analyses"] = {}
        try:
            for index, item in enumerate(selected, 1):
                analysis_status.text = f"Analisando {index}/{len(selected)}: {item['name']}"
                analysis = await run.io_bound(analyze_video, item["path"], settings)
                entry = {"analysis": analysis, "mode": "around_dialogues"}
                entry["plan"] = plan_for(analysis, entry["mode"])
                state["analyses"][item["path"]] = entry
                analysis_progress.value = index / len(selected)
            analysis_status.text = f"Análise concluída: {len(selected)} vídeo(s)"
            _render_results()
        except Exception as exc:
            analysis_status.text = f"Falha: {exc}"
            ui.notify(f"Análise falhou: {exc}", type="negative", multi_line=True)
        finally:
            analyze_button.enable()

    async def _process_selected() -> None:
        if not state["analyses"]:
            return
        destination = Path(output_dir.value).expanduser()
        process_button.disable()
        process_progress.set_visibility(True)
        process_progress.value = 0
        processed_box.clear()
        entries = list(state["analyses"].items())
        completed = 0
        try:
            for index, (path, entry) in enumerate(entries, 1):
                process_status.text = f"Processando {index}/{len(entries)}: {Path(path).name}"
                output, plan_path = await run.io_bound(render_plan, entry["plan"], destination)
                key = _media_key(str(output))
                RESULT_REGISTRY[key] = str(output)
                completed += 1
                process_progress.value = completed / len(entries)
                with processed_box:
                    with ui.card().classes("w-full"):
                        ui.label(output.name).classes("font-bold")
                        ui.video(f"/silence-result/{key}").classes("w-full max-w-2xl")
                        ui.label(f"Vídeo: {output}").classes("text-xs opacity-70")
                        ui.label(f"Plano JSON: {plan_path}").classes("text-xs opacity-70")
            process_status.text = f"Concluído. {completed} vídeo(s) em: {destination.resolve()}"
            ui.notify(f"Vídeos salvos em {destination.resolve()}", type="positive", multi_line=True)
        except Exception as exc:
            process_status.text = f"Falha: {exc}"
            ui.notify(f"Processamento falhou: {exc}", type="negative", multi_line=True)
        finally:
            process_button.enable()

    browse.on_click(_choose_folder)
    load_button.on_click(_load_files)
    select_all.on_click(lambda: _set_selection(True))
    select_none.on_click(lambda: _set_selection(False))
    invert.on_click(lambda: _set_selection(None))
    analyze_button.on_click(_analyze_selected)
    process_button.on_click(_process_selected)
