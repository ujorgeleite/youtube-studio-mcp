"""Cockpit do roughcut — UI de testes no navegador (NiceGUI).

Adapter fino: dispara o pipeline via run.py, transmite o events.jsonl ao vivo,
mostra o stringout e navega os runs anteriores. Nenhuma lógica de pipeline vive
aqui. Rodar: `make cockpit` (ou `python cockpit/app.py`).
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
from cockpit.runs import RUNS_DIR, list_runs, read_events, zip_run  # noqa: E402
from steps.run_record import RunRecord  # noqa: E402

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]

RUNS_DIR.mkdir(parents=True, exist_ok=True)
app.add_media_files("/runs", str(RUNS_DIR))


def _format_event(event: dict) -> str:
    step = event.get("step", "?")
    name = event.get("event", "?")
    level = event.get("level", "info")
    payload = event.get("payload") or {}
    elapsed = event.get("elapsed_ms", 0)
    mark = "✗" if level == "error" else "•"
    extra = " ".join(f"{k}={_short(v)}" for k, v in payload.items())
    return f"{mark} [{elapsed:>6} ms] {step}/{name} {extra}".rstrip()


def _short(value: object, limit: int = 80) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Tailer:
    """Empurra novas linhas do events.jsonl para o ui.log, mantendo o offset."""

    def __init__(self, events_file: Path, log: ui.log):
        self._file = events_file
        self._log = log
        self._pos = 0

    def poll(self) -> None:
        if not self._file.is_file():
            return
        with self._file.open(encoding="utf-8") as fh:
            fh.seek(self._pos)
            for line in fh:
                if line.strip():
                    self._log.push(_format_event(json.loads(line)))
            self._pos = fh.tell()


@ui.page("/")
def cockpit() -> None:
    ui.query("body").style("background-color: #0e1117")
    with ui.header().classes("items-center"):
        ui.label("roughcut — cockpit").classes("text-lg font-bold")
        ui.space()
        ui.label("pré-montagem + logs ricos por run").classes("text-sm opacity-70")

    with ui.row().classes("w-full no-wrap gap-4 p-4"):
        with ui.card().classes("w-96"):
            ui.label("Novo run").classes("text-base font-bold")
            mode = ui.select(
                {"dry": "dry-run (assemble, sem LLM/Whisper)", "full": "completo (LLM + Whisper)"},
                value="dry",
                label="Modo",
            ).classes("w-full")
            input_dir = ui.input("Pasta de clipes", placeholder="vazio no dry-run = clipes de demo").classes("w-full")
            fmt = ui.select(pipeline.list_formats() or ["qualidade-de-vida"], label="Formato").classes("w-full")
            fmt.value = fmt.options[0] if fmt.options else None
            model = ui.select(MODEL_SIZES, value="base", label="Modelo Whisper").classes("w-full")
            run_button = ui.button("Rodar pipeline", icon="play_arrow").classes("w-full")

            def _toggle_full_fields() -> None:
                is_full = mode.value == "full"
                fmt.set_visibility(is_full)
                model.set_visibility(is_full)

            mode.on_value_change(lambda _: _toggle_full_fields())
            _toggle_full_fields()

        with ui.card().classes("flex-grow"):
            ui.label("Log ao vivo").classes("text-base font-bold")
            status = ui.label("aguardando…").classes("text-sm opacity-70")
            log = ui.log(max_lines=2000).classes("w-full h-80 bg-black text-green-300 text-xs")
            results = ui.column().classes("w-full")

    ui.separator()
    ui.label("Runs anteriores").classes("text-base font-bold px-4")
    runs_panel = ui.column().classes("w-full p-4 gap-2")

    def _show_results(record: RunRecord) -> None:
        results.clear()
        manifest = json.loads((record.dir / "run.json").read_text(encoding="utf-8"))
        video = record.dir / "stringout.mp4"
        with results:
            if video.is_file():
                ui.video(f"/runs/{record.dir.name}/stringout.mp4").classes("w-full max-w-2xl")
            critica_file = record.dir / "critica.json"
            if critica_file.is_file():
                with ui.expansion("Crítica da ordenação", icon="rate_review").classes("w-full"):
                    ui.code(critica_file.read_text(encoding="utf-8"), language="json")
            ui.button(
                "Baixar bundle (zip para IA)",
                icon="download",
                on_click=lambda: ui.download(str(zip_run(record.dir))),
            )
            ui.label(f"bundle: {record.dir}").classes("text-xs opacity-60")

    async def _start_run() -> None:
        if mode.value == "full" and not input_dir.value:
            ui.notify("Pasta de clipes é obrigatória no modo completo", type="warning")
            return

        run_button.disable()
        log.clear()
        results.clear()
        status.text = "rodando…"

        params = {
            "mode": mode.value,
            "format": fmt.value,
            "model_size": model.value,
            "input": input_dir.value or None,
            "output": None,
        }
        record = RunRecord.create(RUNS_DIR, params)
        output = str(record.dir / "stringout.mp4")
        tailer = Tailer(record.dir / "events.jsonl", log)
        timer = ui.timer(0.4, tailer.poll)
        try:
            if mode.value == "dry":
                await run.io_bound(
                    pipeline.run_dry, output=output, input=input_dir.value or None, record=record
                )
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
            _show_results(record)
        except Exception as exc:
            status.text = f"erro: {exc}"
            ui.notify(f"Run falhou: {exc}", type="negative", multi_line=True)
        finally:
            timer.deactivate()
            tailer.poll()
            run_button.enable()
            _refresh_runs()

    run_button.on_click(_start_run)

    def _refresh_runs() -> None:
        runs_panel.clear()
        runs = list_runs()
        with runs_panel:
            if not runs:
                ui.label("nenhum run ainda").classes("text-sm opacity-60")
                return
            for entry in runs:
                manifest = entry["manifest"] or {}
                icon = "check_circle" if entry["status"] == "ok" else (
                    "error" if entry["status"] == "error" else "help"
                )
                with ui.expansion(entry["run_id"], icon=icon).classes("w-full"):
                    duration = manifest.get("duration_ms")
                    ui.label(
                        f"status={entry['status']}  duração={duration} ms  "
                        f"passos={[s['step'] for s in manifest.get('steps', [])]}"
                    ).classes("text-xs opacity-70")
                    events = read_events(entry["dir"])
                    ui.code("\n".join(_format_event(e) for e in events) or "(sem eventos)").classes("w-full")
                    ui.button(
                        "Baixar bundle (zip)",
                        icon="download",
                        on_click=lambda d=entry["dir"]: ui.download(str(zip_run(d))),
                    ).props("flat")

    _refresh_runs()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="roughcut cockpit", port=8080, reload=False, show=True)
