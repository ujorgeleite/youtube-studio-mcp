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
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from nicegui import app, run, ui  # noqa: E402

import run as pipeline  # noqa: E402
from cockpit import preview  # noqa: E402
from cockpit import silence as silence_page  # noqa: E402,F401
from cockpit.filepicker import choose_directory  # noqa: E402
from cockpit.runs import (  # noqa: E402
    RUNS_DIR,
    delete_run,
    human_size,
    list_runs,
    read_events,
    zip_run,
)
from steps.assemble import parse_timecode  # noqa: E402
from steps.frames import clip_duration, cold_open_frames, first_frames, grid_frames  # noqa: E402
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

CLIP_REGISTRY: dict[str, dict[str, str]] = {}

# Player da prévia: toca os trechos direto dos clipes de origem (%SEGS% é injetado),
# pulando de segmento em segmento sem renderizar nada — é só pré-visualização.
_PLAYER_JS = """
(() => {
  const v = document.getElementById('rc-preview');
  if (!v) return;
  const segs = %SEGS%;
  let i = 0;
  function load(k){ const s = segs[k]; if(!s) return;
    if (v.dataset.src !== s.url){ v.dataset.src = s.url; v.src = s.url; v.load(); }
    else { v.currentTime = s.inS; v.play(); } }
  v.onloadedmetadata = () => { const s = segs[i]; if (s){ v.currentTime = s.inS; v.play(); } };
  v.ontimeupdate = () => { const s = segs[i];
    if (s && v.currentTime >= s.outS){ i++; if (i < segs.length) load(i); else v.pause(); } };
  i = 0; if (segs.length) load(0);
})();
"""


@app.get("/clip/{run_id}/{clip_id}")
def _serve_clip(run_id: str, clip_id: str):
    path = CLIP_REGISTRY.get(run_id, {}).get(clip_id)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404)
    return FileResponse(path)


def _tc(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


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
    ui.dark_mode().enable()
    manual_state: dict = {}
    last_run: dict = {}
    assemble_state: dict[str, float] = {}

    with ui.header().classes("items-center"):
        ui.label("roughcut — cockpit").classes("text-lg font-bold")
        ui.link("Pré-montagem", "/").classes("text-sm text-amber-300 font-bold")
        ui.link("Remover silêncios", "/silence").classes("text-sm text-white")
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
        assemble_label = ui.label("").classes("text-sm font-medium")
        assemble_label.set_visibility(False)
        assemble_progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
        assemble_progress.set_visibility(False)
        with ui.expansion("Detalhes técnicos (log ao vivo)", icon="terminal").classes("w-full mt-2"):
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
        elif step == "assemble" and name == "segment_start":
            assemble_state.setdefault("started", time.monotonic())
            total_seconds = float(payload["total_seconds"])
            completed_seconds = float(payload["completed_seconds"])
            assemble_progress.set_visibility(True)
            assemble_progress.value = completed_seconds / total_seconds if total_seconds else 0.0
            assemble_label.set_visibility(True)
            source = payload.get("clip_id", "B-roll")
            assemble_label.text = (
                f"Montando trecho {payload['index']}/{payload['total']}: {source} "
                f"({_tc(float(payload['seconds']))})"
            )
            timeline.set("assemble", MARK_ACTIVE, sub=f"trecho {payload['index']}/{payload['total']}")
        elif step == "assemble" and name == "segment_done":
            total_seconds = float(payload["total_seconds"])
            completed_seconds = float(payload["completed_seconds"])
            progress = completed_seconds / total_seconds if total_seconds else 0.0
            assemble_progress.value = progress
            elapsed = time.monotonic() - assemble_state.setdefault("started", time.monotonic())
            remaining = elapsed * (1 - progress) / progress if progress else 0.0
            assemble_label.text = (
                f"Montagem {payload['index']}/{payload['total']} · {progress:.0%} "
                f"· cerca de {_tc(remaining)} restantes"
            )
        elif step == "assemble" and name == "concat_start":
            assemble_label.set_visibility(True)
            assemble_label.text = "Unindo os trechos e finalizando o arquivo…"
            assemble_progress.value = 0.99
        elif step == "assemble" and name == "concat_done":
            assemble_progress.value = 1.0
            assemble_label.text = "Vídeo finalizado — preparando a prévia…"

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
        assemble_state.clear()
        assemble_label.set_visibility(False)
        assemble_progress.set_visibility(False)

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

    def _loading(text: str) -> None:
        spinner.set_visibility(True)
        status.text = text
        manual_area.clear()
        with manual_area:
            with ui.row().classes("items-center gap-3 p-4"):
                ui.spinner(size="lg")
                ui.label(text).classes("text-sm opacity-80")

    async def _finish_manual(raw: str) -> None:
        if not raw or not raw.strip():
            ui.notify("Cole a resposta da IA primeiro", type="warning")
            return
        record = manual_state["record"]
        _loading("Processando a resposta da IA…")
        try:
            cut_list = await run.io_bound(pipeline.record_response, record, raw)
        except Exception as exc:
            ui.notify(f"JSON inválido: {exc}", type="negative", multi_line=True)
            _show_manual(manual_state["prompt"], raw=raw, error=str(exc))
            _refresh_runs()
            return
        manual_state["cut_list"] = cut_list
        CLIP_REGISTRY[record.dir.name] = manual_state["clip_map"]
        _loading("Gerando miniaturas dos clipes…")
        manual_state["thumbs"] = await run.io_bound(
            first_frames, manual_state["clip_map"], str(record.dir / "frames")
        )
        _show_editor()
        _refresh_runs()

    async def _play_preview() -> None:
        segments = [
            {
                "url": f"/clip/{manual_state['record'].dir.name}/{s['clip_id']}",
                "inS": parse_timecode(s["in"]),
                "outS": parse_timecode(s["out"]),
            }
            for s in preview.player_segments(manual_state["cut_list"])
        ]
        if not segments:
            ui.notify("Nenhum trecho com clipe para tocar", type="warning")
            return
        await ui.run_javascript(_PLAYER_JS.replace("%SEGS%", json.dumps(segments)))

    def _timeline_card(idx: int, beat: dict, run_id: str, thumbs: dict) -> None:
        clips = beat.get("clips") or []
        is_broll = not clips
        with ui.card().classes("shrink-0 w-40 p-1 gap-1"):
            with ui.row().classes("items-center gap-1 w-full"):
                ui.label(str(idx + 1)).classes(
                    "text-xs font-bold bg-primary text-white rounded px-1"
                )
                ui.label(beat.get("beat", "")).classes("text-xs font-medium truncate flex-grow")
            thumb = thumbs.get(clips[0]["clip_id"]) if clips else None
            if thumb:
                ui.image(f"/runs/{run_id}/frames/{thumb}").classes("w-full rounded").style(
                    "height:80px;object-fit:cover"
                )
            else:
                with ui.element("div").classes(
                    "w-full rounded flex items-center justify-center bg-neutral-800"
                ).style("height:80px"):
                    ui.label("B-ROLL").classes("text-xs opacity-70")
            if is_broll:
                ui.label(beat.get("broll_suggestion") or "(sem sugestão)").classes(
                    "text-xs opacity-60 truncate"
                )
            else:
                first = clips[0]
                extra = f" +{len(clips) - 1}" if len(clips) > 1 else ""
                ui.label(f"{first['clip_id']} {first.get('in')}–{first.get('out')}{extra}").classes(
                    "text-xs opacity-70 truncate"
                )
            with ui.row().classes("justify-center gap-0 w-full"):
                ui.button(icon="chevron_left", on_click=lambda i=idx: _move(i, -1)).props(
                    "flat dense round size=sm"
                )
                ui.button(icon="chevron_right", on_click=lambda i=idx: _move(i, 1)).props(
                    "flat dense round size=sm"
                )
                ui.button(icon="close", color="red", on_click=lambda i=idx: _remove(i)).props(
                    "flat dense round size=sm"
                )

    def _show_editor() -> None:
        spinner.set_visibility(False)
        status.text = "prévia — aprove ou reordene antes de montar"
        manual_area.clear()
        cut_list = manual_state["cut_list"]
        run_id = manual_state["record"].dir.name
        thumbs = manual_state.get("thumbs", {})
        beats = cut_list.get("roughcut", [])
        leftovers = preview.leftover_clips(cut_list, manual_state["clip_map"])
        with manual_area:
            with ui.card().classes("w-full items-center bg-black"):
                ui.html(
                    '<video id="rc-preview" controls playsinline '
                    'style="width:100%;max-width:760px;border-radius:8px;background:#000"></video>'
                )
                ui.button("Reproduzir prévia", icon="play_arrow", on_click=_play_preview)

            ui.label(f"No vídeo — em ordem ({len(beats)} cortes)").classes("text-sm font-bold mt-3")
            with ui.row().classes("w-full gap-2 pb-2 items-stretch").style(
                "flex-wrap:nowrap;overflow-x:auto"
            ):
                for idx, beat in enumerate(beats):
                    _timeline_card(idx, beat, run_id, thumbs)

            ui.label(f"Fora do vídeo — clipes não usados ({len(leftovers)})").classes(
                "text-sm font-bold mt-3"
            )
            if not leftovers:
                ui.label("todos os clipes estão no vídeo").classes("text-xs opacity-60")
            with ui.row().classes("w-full gap-2 pb-2 items-stretch").style(
                "flex-wrap:nowrap;overflow-x:auto"
            ):
                for clip_id in leftovers:
                    with ui.card().classes("shrink-0 w-32 p-1 gap-1 opacity-80"):
                        if clip_id in thumbs:
                            ui.image(f"/runs/{run_id}/frames/{thumbs[clip_id]}").classes(
                                "w-full rounded"
                            ).style("height:64px;object-fit:cover")
                        ui.label(clip_id).classes("text-xs opacity-70 text-center")
                        ui.button(
                            "Inserir", icon="add", on_click=lambda c=clip_id: _insert(c)
                        ).props("flat dense size=sm").classes("w-full")

            with ui.row().classes("mt-4 gap-2"):
                ui.button("Aprovar e montar", icon="check", color="green", on_click=_approve)
                ui.button("Cancelar", on_click=lambda: _new_run()).props("flat")

    def _move(index: int, delta: int) -> None:
        preview.move_beat(manual_state["cut_list"], index, delta)
        _show_editor()

    def _remove(index: int) -> None:
        preview.remove_beat(manual_state["cut_list"], index)
        _show_editor()

    async def _insert(clip_id: str) -> None:
        duration = await run.io_bound(clip_duration, manual_state["clip_map"][clip_id])
        preview.insert_clip(manual_state["cut_list"], clip_id, "00:00:00", _tc(duration))
        _show_editor()

    async def _approve() -> None:
        with monitor_card:
            record = manual_state["record"]
            _loading("Montando o vídeo final (ffmpeg)…")
            timer = ui.timer(0.4, manual_state["tailer"].poll)
            try:
                await run.io_bound(
                    pipeline.assemble_approved,
                    cut_list=manual_state["cut_list"],
                    clip_map=manual_state["clip_map"],
                    output=manual_state["output"],
                    record=record,
                )
                status.text = "concluído ✓"
                last_run.update(record=record, clip_map=manual_state["clip_map"])
                manual_area.clear()
                _show_results(record)
            except Exception as exc:
                status.text = f"erro: {exc}"
                ui.notify(f"Falha ao montar: {exc}", type="negative", multi_line=True)
                _show_editor()
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
