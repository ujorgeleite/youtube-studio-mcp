"""Cockpit do roughcut — UI de testes no navegador (NiceGUI).

Adapter fino: dispara o pipeline via run.py, transmite o events.jsonl ao vivo numa
timeline de etapas, mostra o stringout, extrai frames de ganchos sob demanda e
navega os runs anteriores. Nenhuma lógica de pipeline vive aqui.
Rodar: `make cockpit` (ou `python cockpit/app.py`).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from nicegui import app, run, ui  # noqa: E402

import run as pipeline  # noqa: E402
from cockpit.filepicker import choose_directory  # noqa: E402
from cockpit.runs import (  # noqa: E402
    RUNS_DIR,
    delete_run,
    human_size,
    list_runs,
    read_events,
    zip_run,
)
from steps.frames import cold_open_frames, grid_frames  # noqa: E402
from steps.run_record import RunRecord  # noqa: E402

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]

STEP_LABELS = {
    "transcribe": "Transcrição (Whisper)",
    "order": "Ordenação",
    "assemble": "Montagem (ffmpeg)",
}
MARK_PENDING, MARK_ACTIVE, MARK_DONE, MARK_ERROR, MARK_WAIT = "⚪", "⏳", "✅", "❌", "✋"

RUNS_DIR.mkdir(parents=True, exist_ok=True)
app.add_media_files("/runs", str(RUNS_DIR))


def _short(value: object, limit: int = 80) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_event(event: dict) -> str:
    payload = event.get("payload") or {}
    extra = " ".join(f"{k}={_short(v)}" for k, v in payload.items())
    mark = "✗" if event.get("level") == "error" else "•"
    return f"{mark} [{event.get('elapsed_ms', 0):>6} ms] {event.get('step')}/{event.get('event')} {extra}".rstrip()


class Tailer:
    """Lê novas linhas do events.jsonl e entrega cada evento a um callback."""

    def __init__(self, events_file: Path, on_event):
        self._file = events_file
        self._on_event = on_event
        self._pos = 0

    def poll(self) -> None:
        if not self._file.is_file():
            return
        with self._file.open(encoding="utf-8") as fh:
            fh.seek(self._pos)
            for line in fh:
                if line.strip():
                    self._on_event(json.loads(line))
            self._pos = fh.tell()


class Timeline:
    """Etapas do run com marcador de estado, criadas sob demanda por evento."""

    def __init__(self, container):
        self._container = container
        self._rows: dict[str, tuple] = {}

    def reset(self) -> None:
        self._container.clear()
        self._rows = {}

    def _row(self, step: str):
        if step not in self._rows:
            with self._container:
                with ui.row().classes("items-center gap-2"):
                    mark = ui.label(MARK_PENDING)
                    name = ui.label(STEP_LABELS.get(step, step)).classes("font-medium")
                    sub = ui.label("").classes("text-xs opacity-70")
            self._rows[step] = (mark, name, sub)
        return self._rows[step]

    def set(self, step: str, marker: str, sub: str | None = None) -> None:
        mark, _, sub_label = self._row(step)
        mark.text = marker
        if sub is not None:
            sub_label.text = sub


@ui.page("/")
def cockpit() -> None:
    ui.query("body").style("background-color: #0e1117")
    manual_state: dict = {}
    last_run: dict = {}

    with ui.header().classes("items-center"):
        ui.label("roughcut — cockpit").classes("text-lg font-bold")
        ui.space()
        ui.label("pré-montagem + logs ricos por run").classes("text-sm opacity-70")

    controls_card = ui.card().classes("w-full max-w-xl m-4")
    with controls_card:
        ui.label("Novo run").classes("text-base font-bold")
        mode = ui.select(
            {
                "dry": "dry-run (assemble, sem LLM/Whisper)",
                "full": "completo — IA via API (ANTHROPIC_API_KEY)",
                "manual": "manual — copiar prompt / colar resposta",
            },
            value="dry",
            label="Modo",
        ).classes("w-full")
        with ui.row().classes("w-full items-end no-wrap gap-1"):
            input_dir = ui.input(
                "Pasta de clipes", placeholder="vazio no dry-run = clipes de demo"
            ).classes("flex-grow")

            async def _browse() -> None:
                chosen = await run.io_bound(choose_directory)
                if chosen:
                    input_dir.value = chosen

            ui.button(icon="folder_open", on_click=_browse).props("flat dense").tooltip(
                "Procurar pasta no sistema…"
            )
        fmt = ui.select(pipeline.list_formats() or ["qualidade-de-vida"], label="Formato").classes("w-full")
        fmt.value = fmt.options[0] if fmt.options else None
        model = ui.select(MODEL_SIZES, value="base", label="Modelo Whisper").classes("w-full")
        run_button = ui.button("Rodar pipeline", icon="play_arrow").classes("w-full")

        def _toggle_fields() -> None:
            needs_ai = mode.value in ("full", "manual")
            fmt.set_visibility(needs_ai)
            model.set_visibility(needs_ai)
            run_button.text = "Preparar prompt" if mode.value == "manual" else "Rodar pipeline"

        mode.on_value_change(lambda _: _toggle_fields())
        _toggle_fields()

    monitor_card = ui.card().classes("w-full m-4")
    monitor_card.set_visibility(False)
    with monitor_card:
        with ui.row().classes("items-center gap-2 w-full"):
            spinner = ui.spinner(size="lg")
            status = ui.label("aguardando…").classes("text-base font-medium")
            ui.space()
            new_run_button = ui.button("Novo run", icon="add", on_click=lambda: _new_run()).props("outline")
            new_run_button.set_visibility(False)
        timeline_box = ui.column().classes("gap-1")
        timeline = Timeline(timeline_box)
        clip_label = ui.label("").classes("text-sm")
        clip_progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
        clip_progress.set_visibility(False)
        ui.label("Log ao vivo").classes("text-sm font-bold mt-2")
        log = ui.log(max_lines=2000).classes("w-full h-64 bg-black text-green-300 text-xs")
        manual_area = ui.column().classes("w-full")
        results = ui.column().classes("w-full")

    ui.separator()
    ui.label("Runs anteriores").classes("text-base font-bold px-4")
    runs_panel = ui.column().classes("w-full p-4 gap-2")

    def _on_event(event: dict) -> None:
        log.push(_format_event(event))
        step = event.get("step")
        name = event.get("event")
        payload = event.get("payload") or {}
        if name == "step_start":
            timeline.set(step, MARK_ACTIVE)
        elif name == "step_end":
            timeline.set(step, MARK_DONE)
        elif name == "step_error":
            timeline.set(step, MARK_ERROR, sub=payload.get("error", ""))
        elif step == "transcribe" and name == "clip":
            total = payload.get("total") or 1
            index = payload.get("index") or 0
            clip_progress.set_visibility(True)
            clip_progress.value = index / total
            clip_label.text = (
                f"analisando clipe {index}/{total}: {payload.get('clip_id')} "
                f"({payload.get('filename')})"
            )
            timeline.set("transcribe", MARK_ACTIVE, sub=f"{index}/{total}")
        elif step == "order" and name == "prompt_ready":
            timeline.set("transcribe", MARK_DONE)
            timeline.set("order", MARK_WAIT, sub="aguardando você colar a resposta")
        elif step == "order" and name == "response_received":
            timeline.set("order", MARK_DONE)

    def _begin_run() -> None:
        controls_card.set_visibility(False)
        monitor_card.set_visibility(True)
        new_run_button.set_visibility(False)
        spinner.set_visibility(True)
        timeline.reset()
        log.clear()
        manual_area.clear()
        results.clear()
        clip_label.text = ""
        clip_progress.set_visibility(False)

    def _new_run() -> None:
        manual_state.clear()
        last_run.clear()
        monitor_card.set_visibility(False)
        controls_card.set_visibility(True)

    def _clips_for(mode_value: str) -> dict | None:
        if mode_value == "manual":
            return manual_state.get("clip_map")
        if input_dir.value:
            return pipeline.list_clips(input_dir.value)
        return None

    def _show_results(record: RunRecord) -> None:
        spinner.set_visibility(False)
        new_run_button.set_visibility(True)
        results.clear()
        video = record.dir / "stringout.mp4"
        with results:
            if video.is_file():
                ui.video(f"/runs/{record.dir.name}/stringout.mp4").classes("w-full max-w-2xl")
            critica_file = record.dir / "critica.json"
            if critica_file.is_file():
                with ui.expansion("Crítica da ordenação", icon="rate_review").classes("w-full"):
                    ui.code(critica_file.read_text(encoding="utf-8"), language="json")

            frames_box = ui.column().classes("w-full")
            hook_button = ui.button("Extrair frames de ganchos", icon="image")
            if not last_run.get("clip_map"):
                hook_button.disable()
                hook_button.tooltip("Sem clipes reais neste run (dry-run de demonstração)")

            async def _extract_hooks() -> None:
                hook_button.disable()
                frames_box.clear()
                with frames_box:
                    ui.spinner()
                    note = ui.label("extraindo frames…").classes("text-sm opacity-70")
                clip_map = last_run["clip_map"]
                cut_list = {}
                cut_file = record.dir / "cut-list.json"
                if cut_file.is_file():
                    cut_list = json.loads(cut_file.read_text(encoding="utf-8"))
                out_dir = str(record.dir / "frames")
                try:
                    grid = await run.io_bound(grid_frames, clip_map, out_dir)
                    cold = await run.io_bound(cold_open_frames, cut_list, clip_map, out_dir)
                except Exception as exc:
                    note.text = f"erro: {exc}"
                    hook_button.enable()
                    return
                record.event("frames", "extracted", grid=len(grid), cold_open=len(cold))
                _render_frames(frames_box, record.dir.name, cold, grid)
                hook_button.enable()

            hook_button.on_click(_extract_hooks)

            ui.button(
                "Baixar bundle (zip para IA)",
                icon="download",
                on_click=lambda: ui.download(str(zip_run(record.dir))),
            ).props("flat")
            ui.label(f"bundle: {record.dir}").classes("text-xs opacity-60")

    def _render_frames(box, run_id: str, cold: list[dict], grid: list[dict]) -> None:
        box.clear()
        with box:
            if cold:
                ui.label("Ganchos (cold_open)").classes("text-sm font-bold text-amber-400")
                with ui.row().classes("flex-wrap gap-2"):
                    for f in cold:
                        with ui.column().classes("items-center gap-0"):
                            ui.image(f"/runs/{run_id}/frames/{f['path']}").classes("w-48 rounded")
                            ui.label(f"{f['clip_id']} @ {f['at_s']}s").classes("text-xs opacity-70")
            if grid:
                ui.label("Todos os clipes (grade)").classes("text-sm font-bold mt-2")
                with ui.row().classes("flex-wrap gap-2"):
                    for f in grid:
                        with ui.column().classes("items-center gap-0"):
                            ui.image(f"/runs/{run_id}/frames/{f['path']}").classes("w-32 rounded")
                            ui.label(f"{f['clip_id']} @ {f['at_s']}s").classes("text-xs opacity-60")
            if not cold and not grid:
                ui.label("nenhum frame extraído").classes("text-sm opacity-60")

    def _show_manual(prompt: str, raw: str = "", error: str | None = None) -> None:
        spinner.set_visibility(False)
        manual_area.clear()
        with manual_area:
            if error:
                ui.label(f"Falha ao processar a resposta: {error}").classes(
                    "text-sm text-red-400 font-medium"
                )
                ui.label("Corrija o JSON abaixo e tente de novo.").classes("text-xs opacity-70")
            ui.label("1) Copie este prompt e rode na IA de sua preferência").classes("text-sm font-bold")
            ui.textarea(value=prompt).props("readonly outlined").classes("w-full h-40 font-mono text-xs")

            async def _copy() -> None:
                try:
                    await ui.clipboard.write(prompt)
                    ui.notify("Prompt copiado", type="positive")
                except Exception:
                    ui.notify("Copie manualmente pelo campo acima", type="warning")

            ui.button("Copiar prompt", icon="content_copy", on_click=_copy).props("outline")
            ui.label("2) Cole aqui a resposta da IA (o JSON da cut-list)").classes("text-sm font-bold")
            response_box = ui.textarea(value=raw, placeholder='{ "roughcut": [ ... ] }').props(
                "outlined"
            ).classes("w-full h-40 font-mono text-xs")
            ui.button(
                "Montar stringout com esta resposta",
                icon="build",
                on_click=lambda: _finish_manual(response_box.value),
            )

    async def _finish_manual(raw: str) -> None:
        if not raw or not raw.strip():
            ui.notify("Cole a resposta da IA primeiro", type="warning")
            return
        record = manual_state["record"]
        spinner.set_visibility(True)
        status.text = "montando…"
        manual_area.clear()
        timer = ui.timer(0.4, manual_state["tailer"].poll)
        try:
            await run.io_bound(
                pipeline.assemble_from_raw,
                raw=raw,
                clip_map=manual_state["clip_map"],
                output=manual_state["output"],
                record=record,
            )
            status.text = "concluído ✓"
            last_run.update(record=record, clip_map=manual_state["clip_map"])
            _show_results(record)
        except Exception as exc:
            status.text = "erro na resposta — corrija e tente de novo"
            ui.notify(f"Falha ao montar: {exc}", type="negative", multi_line=True)
            _show_manual(manual_state["prompt"], raw=raw, error=str(exc))
        finally:
            timer.deactivate()
            manual_state["tailer"].poll()
            _refresh_runs()

    async def _start_run() -> None:
        if mode.value in ("full", "manual") and not input_dir.value:
            ui.notify("Pasta de clipes é obrigatória neste modo", type="warning")
            return

        _begin_run()
        status.text = "rodando…"
        params = {
            "mode": mode.value,
            "format": fmt.value,
            "model_size": model.value,
            "input": input_dir.value or None,
        }
        record = RunRecord.create(RUNS_DIR, params)
        output = str(record.dir / "stringout.mp4")
        tailer = Tailer(record.dir / "events.jsonl", _on_event)
        timer = ui.timer(0.4, tailer.poll)
        try:
            if mode.value == "dry":
                await run.io_bound(
                    pipeline.run_dry, output=output, input=input_dir.value or None, record=record
                )
                status.text = "concluído ✓"
                last_run.update(record=record, clip_map=_clips_for("dry"))
                _show_results(record)
            elif mode.value == "manual":
                prompt, clip_map = await run.io_bound(
                    pipeline.transcribe_and_prompt,
                    input=input_dir.value,
                    format=fmt.value,
                    model_size=model.value,
                    record=record,
                )
                manual_state.update(
                    record=record, clip_map=clip_map, output=output, tailer=tailer, prompt=prompt
                )
                status.text = "prompt pronto — copie, rode na sua IA e cole a resposta"
                _show_manual(prompt)
            else:
                await run.io_bound(
                    pipeline.run_full,
                    input=input_dir.value,
                    format=fmt.value,
                    output=output,
                    model_size=model.value,
                    record=record,
                )
                status.text = "concluído ✓"
                last_run.update(record=record, clip_map=_clips_for("full"))
                _show_results(record)
        except Exception as exc:
            spinner.set_visibility(False)
            status.text = f"erro: {exc}"
            new_run_button.set_visibility(True)
            ui.notify(f"Run falhou: {exc}", type="negative", multi_line=True)
        finally:
            timer.deactivate()
            tailer.poll()
            _refresh_runs()

    run_button.on_click(_start_run)

    async def _confirm_delete(run_dir: str) -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Excluir os arquivos gerados deste run?").classes("font-medium")
            ui.label(
                "Apaga só o bundle em runs/ (vídeo, logs, frames, zip). A pasta de "
                "clipes de origem não é tocada."
            ).classes("text-xs opacity-70")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancelar", on_click=lambda: dialog.submit("cancel")).props("flat")
                ui.button("Excluir", color="red", on_click=lambda: dialog.submit("delete"))
        if await dialog == "delete":
            try:
                delete_run(run_dir)
                ui.notify("Run excluído", type="positive")
            except Exception as exc:
                ui.notify(f"Falha ao excluir: {exc}", type="negative")
            _refresh_runs()

    def _refresh_runs() -> None:
        runs_panel.clear()
        runs = list_runs()
        with runs_panel:
            if not runs:
                ui.label("nenhum run ainda").classes("text-sm opacity-60")
                return
            total = human_size(sum(r["size_bytes"] for r in runs))
            ui.label(f"{len(runs)} run(s) · {total} em disco").classes("text-xs opacity-60")
            for entry in runs:
                manifest = entry["manifest"] or {}
                icon = "check_circle" if entry["status"] == "ok" else (
                    "error" if entry["status"] == "error" else "help"
                )
                title = f"{entry['run_id']}  ·  {human_size(entry['size_bytes'])}"
                with ui.expansion(title, icon=icon).classes("w-full"):
                    ui.label(
                        f"status={entry['status']}  duração={manifest.get('duration_ms')} ms  "
                        f"passos={[s['step'] for s in manifest.get('steps', [])]}"
                    ).classes("text-xs opacity-70")
                    events = read_events(entry["dir"])
                    ui.code("\n".join(_format_event(e) for e in events) or "(sem eventos)").classes("w-full")
                    with ui.row():
                        ui.button(
                            "Baixar bundle (zip)",
                            icon="download",
                            on_click=lambda d=entry["dir"]: ui.download(str(zip_run(d))),
                        ).props("flat")

                        async def _del(d=entry["dir"]) -> None:
                            await _confirm_delete(d)

                        ui.button("Excluir arquivos", icon="delete", color="red", on_click=_del).props("flat")

    _refresh_runs()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="roughcut cockpit", port=8080, reload=False, show=True)
