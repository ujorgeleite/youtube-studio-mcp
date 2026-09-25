from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from silence.analyze import extract_thumbnail, list_videos, probe_duration
from smartcut.config import CutRules, list_presets, load_rules
from smartcut.cuts import cuts_from_words
from smartcut.batch_report import TERMINAL_STAGES, build_batch_summary, write_batch_summary
from smartcut.pipeline import analyze_clip, default_output_dir
from smartcut.preprocess import PreprocessError, extract_audio, has_audio_stream, normalize_loudness
from smartcut.render import render_with_handles
from smartcut.schema import Cut
from .filepicker import choose_directory
from .review_preview import ReviewPreview

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


def _friendly_error(error: Exception) -> str:
    """Keep operational errors useful without exposing a full ffmpeg trace in the UI."""
    detail = str(error).strip()
    lowered = detail.lower()
    if "does not contain any stream" in lowered or "não contém uma trilha de áudio" in lowered:
        return "Este vídeo não possui uma trilha de áudio utilizável."
    if "invalid argument" in lowered and ("m4a" in lowered or "output" in lowered):
        return "O ffmpeg não conseguiu criar o áudio temporário deste vídeo."
    if "ffmpeg não encontrado" in lowered:
        return "O ffmpeg não está instalado ou não está disponível no PATH."
    if "no such file" in lowered or "not found" in lowered:
        return "O arquivo de origem não foi encontrado."
    if isinstance(error, PreprocessError):
        return "Não foi possível preparar o áudio deste vídeo."
    first_line = next((line.strip() for line in detail.splitlines() if line.strip()), "Erro desconhecido")
    return first_line[:180]


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
.rc-thumb { transition:filter .45s ease; } .rc-queue { background:#111920; border:1px solid #263746; border-radius:9px; }
.rc-event { border-left:2px solid #2dd4bf; background:#10181f; } .rc-progress-label { font-variant-numeric:tabular-nums; }
.rc-report-row { border-left:3px solid #2dd4bf; background:#10181f; border-radius:7px; }
.rc-processing-clock { font-variant-numeric:tabular-nums; letter-spacing:.04em; text-shadow:0 0 28px rgba(45,212,191,.28); }
.rc-metric { min-width:145px; border-radius:10px; } .rc-report-complete { border-color:#2dd4bf; background:#102724; } .rc-report-failed { border-color:#fb7185; background:#2a1820; } .rc-report-skipped { border-color:#fbbf24; background:#2a2415; }
.rc-source-bar { background:linear-gradient(100deg,#14212b,#15282a); border:1px solid #36515c; border-radius:14px; } .rc-step { color:#2dd4bf; font-size:11px; font-weight:700; letter-spacing:.08em; }
.rc-source-input .q-field__control { background:#0e161c; border-radius:9px; } .rc-source-input .q-field__label { color:#9fb3c8; }
</style>""")
    state = {
        "files": [], "selected": None, "running": False, "active_cut": None,
        "syncing_rules": False, "events": [], "batch": None, "batch_artifacts": {},
        "operational_mode": None, "rules_mounted": False,
    }

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
        with ui.card().classes("rc-source-bar w-full p-3"):
            with ui.row().classes("w-full items-center gap-3").style("flex-wrap:wrap"):
                ui.icon("folder_copy", size="md").classes("text-teal-300 rounded p-2").style("background:#164e4a")
                with ui.column().classes("gap-0 min-w-44"):
                    ui.label("ORIGEM DO LOTE").classes("rc-step")
                    ui.label("Escolha a pasta raw para começar").classes("text-sm font-bold")
                folder = ui.input("1 · Pasta raw", placeholder="/caminho/para/raw").classes("rc-source-input flex-grow min-w-80")
                browse = ui.button("Escolher pasta", icon="folder_open").props("no-caps outline").classes("text-sm")
                load = ui.button("2 · Carregar vídeos", icon="video_library", color="primary").props("no-caps").classes("font-bold")
                ui.separator().props("vertical").classes("h-12")
                with ui.column().classes("gap-0 min-w-36"):
                    ui.label("DESTINO").classes("rc-step")
                    ui.label("saída organizada").classes("text-xs rc-muted")
                output = ui.input("3 · Pasta de saída", placeholder="gerada ao carregar vídeos").classes("rc-source-input flex-grow min-w-80")
        with ui.row().classes("w-full gap-3 items-stretch").style("flex-wrap:nowrap; min-height:640px"):
            with ui.card().classes("rc-card w-1/4 min-w-72 p-4") as rules_panel:
                ui.label("Regras de corte").classes("font-bold")
                ui.label("preset · ajuste fino antes de processar").classes("text-xs rc-muted")
                rules_box = ui.column().classes("w-full gap-3 mt-3")
                ui.separator().classes("my-1")
                ui.label("Áudio (opcional)").classes("font-bold text-sm")
                denoise = ui.checkbox("Denoise DeepFilterNet").classes("text-sm rc-muted"); denoise.disable()
                normalize = ui.checkbox("Normalizar para -14 LUFS", value=True).classes("text-sm")
                ui.separator()
                analyze = ui.button("Analisar selecionados", icon="graphic_eq", color="primary").props("no-caps").classes("w-full")
            with ui.card().classes("rc-card flex-grow min-w-0 p-4") as review_panel:
                with ui.row().classes("w-full items-center"):
                    ui.label("Timeline de revisão").classes("font-bold flex-grow")
                    ui.label("■ corte proposto").classes("text-xs text-pink-400")
                    ui.label("■ mantido").classes("text-xs text-teal-300")
                    ui.label("■ pausa protegida").classes("text-xs text-amber-300")
                review_select = ui.select({}, label="Vídeo analisado").classes("w-full mt-2")
                review_select.props("dense outlined")
                review_select.set_visibility(False)
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
                batch_box = ui.column().classes("w-full gap-2 mt-3")
                ui.separator()
                result_box = ui.column().classes("w-full gap-3 mt-3")
            with ui.card().classes("rc-card flex-grow min-w-0 p-8 items-center justify-center") as processing_panel:
                ui.icon("movie_filter", size="3rem").classes("text-teal-300")
                ui.label("PROCESSANDO LOTE").classes("text-sm font-bold tracking-widest text-teal-200 mt-3")
                processing_clock = ui.label("00:00:00").classes("rc-processing-clock text-6xl font-bold text-teal-300 mt-2")
                processing_status = ui.label("Preparando renderização…").classes("text-base rc-muted mt-3")
                processing_details = ui.label("").classes("text-sm text-teal-100 mt-1")
                processing_bar = ui.linear_progress(value=0).props("rounded color=teal track-color=blue-grey-9").classes("w-4/5 mt-5")
            processing_panel.set_visibility(False)
        with ui.card().classes("rc-card w-full p-3"):
            with ui.row().classes("w-full items-center"):
                files_title = ui.label("Arquivos brutos").classes("font-bold flex-grow")
                all_button = ui.button("Selecionar todos").props("flat dense no-caps")
                none_button = ui.button("Limpar").props("flat dense no-caps")
            queue_box = ui.row().classes("w-full gap-2 mt-2")
            activity_box = ui.column().classes("w-full gap-1 mt-2")
            files_box = ui.row().classes("w-full gap-2 mt-2").style("flex-wrap:wrap")
            ui.separator().classes("my-2")
            ui.label("RELATÓRIO EM FORMAÇÃO").classes("text-xs font-bold rc-muted")
            report_box = ui.column().classes("w-full gap-2 mt-2")
    with ui.footer().classes("rc-bottom items-center p-4 gap-3"):
        process = ui.button("▶ Processar selecionados", color="teal").props("no-caps").classes("font-bold")
        parallelism = ui.select({1: "1 por vez", 2: "2 em paralelo", 3: "3 em paralelo"}, value=2, label="Renderização").props("dense outlined").classes("w-40")
        status = ui.label("Carregue uma pasta raw para começar.").classes("text-sm rc-muted flex-grow")
        ui.label("VAD em cache ✓").classes("rc-chip")
        progress = ui.linear_progress(value=0).classes("w-48"); progress.set_visibility(False)

    def item() -> dict | None:
        return next((entry for entry in state["files"] if entry["path"] == state["selected"]), None)

    def reviewed_cuts(entry: dict) -> list[Cut]:
        disabled = entry.setdefault("disabled_cuts", set())
        return [cut for index, cut in enumerate(entry["plan"].cuts) if index not in disabled]

    def render_batch_summary() -> None:
        batch_box.clear()
        analyzed = [entry for entry in state["files"] if entry.get("plan")]
        with batch_box:
            ui.label("LOTE ANALISADO").classes("text-xs font-bold rc-muted")
            if not analyzed:
                ui.label("Ainda não há vídeos analisados.").classes("text-xs rc-muted")
                return
            original = sum(entry["duration"] for entry in analyzed)
            removed = sum(sum(cut.end_s - cut.start_s for cut in reviewed_cuts(entry)) for entry in analyzed)
            final = max(0, original - removed)
            rendered = sum(1 for entry in analyzed if entry.get("rendered"))
            working = [entry for entry in state["files"] if entry.get("stage") in {"Extraindo áudio", "Normalizando áudio", "Detectando fala e transcrevendo", "Renderizando"}]
            with ui.card().classes("w-full p-3").style("background:#14262a;border:1px solid #2dd4bf"):
                ui.label(f"{_clock(original, brief=True)} → {_clock(final, brief=True)}").classes("text-lg font-bold text-teal-300")
                ui.label(f"{len(analyzed)} vídeos · {removed:.1f}s removidos · −{100 * removed / original:.1f}%").classes("text-xs text-teal-100")
                ui.label(f"MP4s: {rendered}/{len(analyzed)} · em andamento: {len(working)}").classes("text-xs rc-muted mt-1")
            batch = state.get("batch")
            if batch:
                elapsed = max(0.0, (datetime.now() - datetime.fromisoformat(batch["started_at"])).total_seconds())
                ui.label(f"Processamento deste lote: {_clock(elapsed, brief=True)} · {batch['mode']}").classes("text-xs text-amber-200")

    def set_processing_layout(active: bool) -> None:
        rules_panel.set_visibility(not active)
        review_panel.set_visibility(not active)
        processing_panel.set_visibility(active)
        files_title.text = "Execução do lote" if active else "Arquivos brutos"
        all_button.set_visibility(not active)
        none_button.set_visibility(not active)

    def render_processing_center() -> None:
        batch = state.get("batch")
        if not batch or state.get("operational_mode") != "render":
            return
        summary = build_batch_summary(batch, state["files"])
        videos = summary["videos"]
        duration = summary["duration"]
        finished = videos["completed"] + videos["failed"] + videos["without_audio"]
        processing_clock.text = _clock(summary["elapsed_s"])
        processing_status.text = f"{finished}/{videos['total']} vídeos finalizados"
        processing_details.text = f"{_clock(duration['removed_s'], brief=True)} de vídeo removido · {videos['in_progress']} em andamento"
        processing_bar.value = min(1.0, finished / max(1, videos["total"]))

    def batch_entries() -> list[dict]:
        batch = state.get("batch") or {}
        targets = set(batch.get("targets", []))
        return [entry for entry in state["files"] if entry["path"] in targets]

    def persist_batch_summary() -> dict | None:
        batch = state.get("batch")
        if not batch or not output.value:
            return None
        summary = build_batch_summary(batch, state["files"])
        state["batch_artifacts"] = write_batch_summary(output.value, summary)
        return summary

    def render_report() -> None:
        report_box.clear()
        batch = state.get("batch")
        if not batch:
            with report_box:
                ui.label("O relatório aparece à medida que os vídeos terminam.").classes("text-xs rc-muted")
            return
        summary = build_batch_summary(batch, state["files"])
        with report_box:
            duration = summary["duration"]
            videos = summary["videos"]
            with ui.row().classes("w-full gap-3").style("flex-wrap:wrap"):
                for title, value, note, color in (
                    ("TEMPO INVESTIDO", _clock(summary["elapsed_s"]), "tempo de processamento", "#172433"),
                    ("VÍDEO REMOVIDO", _clock(duration["removed_s"], brief=True), f"{duration['removed_pct']:.1f}% do lote", "#102f2a"),
                    ("CORTES APLICADOS", str(sum(row["cuts"] for row in summary["rows"])), f"{videos['completed']}/{videos['total']} vídeos concluídos", "#2b2038"),
                ):
                    with ui.card().classes("rc-metric flex-grow p-3").style(f"background:{color};border:1px solid #3c5263"):
                        ui.label(title).classes("text-xs font-bold rc-muted")
                        ui.label(value).classes("text-2xl font-bold text-teal-200")
                        ui.label(note).classes("text-xs rc-muted")
            ui.label(f"STATUS · {videos['completed']} concluídos · {videos['failed']} falhas · {videos['without_audio']} sem áudio · {videos['in_progress']} em andamento").classes("text-xs font-bold text-slate-300 mt-2")
            for row in reversed(summary["rows"]):
                if row["status"] not in TERMINAL_STAGES:
                    continue
                class_name = "rc-report-complete" if row["status"] == "Concluído" else "rc-report-skipped" if row["status"] == "Sem áudio — ignorado" else "rc-report-failed"
                with ui.card().classes(f"rc-report-row {class_name} w-full p-3"):
                    with ui.row().classes("w-full items-center no-wrap"):
                        ui.label(row["name"]).classes("text-base font-bold flex-grow ellipsis")
                        ui.badge(row["status"], color="teal" if row["status"] == "Concluído" else "amber" if row["status"] == "Sem áudio — ignorado" else "negative").classes("text-sm")
                    with ui.row().classes("w-full gap-5 mt-2").style("flex-wrap:wrap"):
                        ui.label(f"{row['cuts']} cortes").classes("text-lg font-bold text-teal-200")
                        ui.label(f"{_clock(row['removed_s'], brief=True)} removido").classes("text-lg font-bold text-teal-200")
                        ui.label(f"{_clock(row['original_s'], brief=True)} → {_clock(row['final_s'], brief=True)}").classes("text-sm rc-muted")
                        ui.label(f"render: {_clock(row['render_s'], brief=True)}").classes("text-sm rc-muted")
                    if row["error"]:
                        ui.label(row["error"]).classes("text-sm text-red-200 mt-1")
            artifacts = state.get("batch_artifacts", {})
            if artifacts:
                ui.label(f"✓ resumo: {artifacts['markdown'].name} · {artifacts['json'].name}").classes("text-xs text-teal-300")

    def start_batch(mode: str, targets: list[dict]) -> None:
        now = datetime.now()
        state["batch"] = {
            "id": now.strftime("%Y%m%d-%H%M%S"), "mode": mode,
            "started_at": now.isoformat(), "targets": [entry["path"] for entry in targets],
        }
        state["batch_artifacts"] = {}
        for entry in targets:
            entry.pop("completed_at", None)
            entry.pop("analysis_elapsed_s", None)
            entry.pop("render_elapsed_s", None)

    def rules_from_controls() -> CutRules:
        return replace(load_rules(preset.value), pause_within_sentence_s=round(within.value, 2), pause_after_sentence_s=round(after.value, 2), breath_padding_s=round(breath.value, 2), min_segment_s=round(minimum.value, 2), audio_crossfade_ms=int(crossfade.value), preserve_dramatic_pauses=protect.value, punch_in=punch.value)

    def set_rules_controls(rules: CutRules) -> None:
        state["syncing_rules"] = True
        try:
            within.set_value(rules.pause_within_sentence_s); after.set_value(rules.pause_after_sentence_s)
            minimum.set_value(rules.min_segment_s); breath.set_value(rules.breath_padding_s)
            crossfade.set_value(rules.audio_crossfade_ms); protect.set_value(rules.preserve_dramatic_pauses)
            punch.set_value(rules.punch_in)
        finally:
            state["syncing_rules"] = False

    def refresh_plan() -> None:
        if state["syncing_rules"]:
            return
        current = item()
        if current and current.get("plan"):
            plan = current["plan"]
            rules = rules_from_controls()
            current["rules"] = rules
            plan.cuts = cuts_from_words(plan.words, rules, plan.protected_pauses if rules.preserve_dramatic_pauses else [])
            for retake in plan.retakes:
                if retake.get("selected"):
                    plan.cuts.append(Cut(retake["start_s"], retake["end_s"], "retake_repetido", transcript_before=retake["text"], transcript_after=retake["kept_text"]))
            plan.cuts.sort(key=lambda cut: cut.start_s)
            state["active_cut"] = None; render_review()

    def render_rules() -> None:
        """Monta os controles uma vez; depois apenas troca os valores do preset."""
        if state["rules_mounted"]:
            set_rules_controls(load_rules(preset.value))
            return
        explanations = {
            "Pausa dentro da frase": (
                "Define o menor silêncio entre duas palavras da mesma frase que vira candidato a corte. "
                "Diminuir encontra mais pausas e cria mais cortes; aumentar preserva mais respiro."
            ),
            "Pausa após fim de frase": (
                "Define o menor silêncio depois de ., !, ? ou … que será reduzido. O valor também é o respiro "
                "mantido nessa transição. Diminuir deixa a fala mais ágil; aumentar preserva cadência entre frases."
            ),
            "Trecho mínimo entre cortes": (
                "Impede cortes muito próximos. Se o trecho de vídeo mantido antes do próximo corte for menor que este valor, "
                "o segundo corte é descartado. Aumentar reduz emendas rápidas."
            ),
            "Respiro preservado": (
                "Em pausas dentro da mesma frase, mantém metade deste tempo antes e metade depois da emenda. "
                "Aumentar deixa a fala mais natural, mas remove menos vídeo."
            ),
            "Crossfade de áudio": (
                "O valor é salvo junto das regras para o plano de edição. O render atual ainda concatena áudio sem crossfade, "
                "portanto mudar este controle não altera o MP4 nesta versão."
            ),
            "Proteger pausas dramáticas": (
                "Quando a análise marcar uma pausa como protegida, ela não será cortada. Desligar permite cortar essas pausas. "
                "A análise atual ainda não marca pausas dramáticas automaticamente em todos os vídeos."
            ),
            "Disfarce de jump cut": (
                "Reserva a regra para aplicar variação visual nas emendas. Ela ainda não é aplicada pelo render atual, "
                "portanto mudar este controle não altera o MP4 nesta versão."
            ),
        }
        with rules_box:
            for title, control, note in (("Pausa dentro da frase", within, "mantém respiro no diálogo"), ("Pausa após fim de frase", after, "preserva intenção editorial"), ("Trecho mínimo entre cortes", minimum, "abaixo disso os cortes se mesclam"), ("Respiro preservado", breath, "nunca corta no meio da palavra"), ("Crossfade de áudio", crossfade, "suaviza a emenda")):
                with ui.row().classes("w-full items-center gap-1"):
                    ui.label(title).classes("text-sm")
                    ui.icon("info_outline", size="16px").classes("text-teal-300 cursor-help").tooltip(explanations[title])
                control.move(rules_box); ui.label(note).classes("text-xs rc-muted")
            with ui.row().classes("w-full items-center gap-1"):
                protect.move()
                ui.icon("info_outline", size="16px").classes("text-teal-300 cursor-help").tooltip(explanations["Proteger pausas dramáticas"])
            with ui.row().classes("w-full items-center gap-1"):
                punch.move()
                ui.icon("info_outline", size="16px").classes("text-teal-300 cursor-help").tooltip(explanations["Disfarce de jump cut"])
        state["rules_mounted"] = True
        set_rules_controls(load_rules(preset.value))

    def render_files() -> None:
        render_queue()
        files_box.clear()
        with files_box:
            entries = state["files"]
            batch = state.get("batch") or {}
            if state.get("operational_mode") == "render":
                targets = set(batch.get("targets", []))
                entries = [
                    entry for entry in entries
                    if entry["path"] in targets and entry.get("stage") not in TERMINAL_STAGES
                ]
            if not entries and state.get("operational_mode") == "render":
                ui.label("Nenhum vídeo aguardando renderização. Consulte o relatório em formação abaixo.").classes("text-sm rc-muted p-3")
            for entry in entries:
                selected_class = "border border-blue-500" if entry["path"] == state["selected"] else ""
                with ui.card().classes(f"rc-card w-48 p-2 {selected_class}"):
                    percent = int(entry.get("progress", 0))
                    image = ui.image(f"/media/{entry['thumb_key']}").classes("rc-thumb w-full rounded bg-black cursor-pointer")
                    image.style(f"height:96px;object-fit:cover;filter:grayscale({100 - percent}%);")
                    image.on("click", lambda _, current=entry: select(current))
                    with ui.row().classes("w-full items-center no-wrap"):
                        check = ui.checkbox(value=entry["selected"]).props("dense")
                        check.on_value_change(lambda event, current=entry: current.update(selected=bool(event.value)))
                        ui.label(entry["name"]).classes("text-xs ellipsis flex-grow")
                    ui.label(_clock(entry["duration"], brief=True)).classes("text-xs rc-muted")
                    with ui.row().classes("w-full items-center gap-1"):
                        ui.linear_progress(value=percent / 100).props("rounded color=teal track-color=blue-grey-9").classes("flex-grow")
                        ui.label(f"{percent}%").classes("rc-progress-label text-xs rc-muted")
                    stage = entry.get("stage", "Pronto para analisar")
                    color = "negative" if stage.startswith("Falhou") else "teal" if stage in {"Cortes prontos", "Concluído"} else "primary" if stage not in {"Pronto para analisar", "Na fila"} else "grey"
                    ui.badge(stage, color=color).props("dense").classes("text-xs")
                    if entry.get("plan"):
                        ui.label(f"{len(entry['plan'].cuts)} cortes propostos").classes("text-xs text-teal-300")
                    if entry.get("error"):
                        ui.label(entry["error"]).classes("text-xs text-red-300 ellipsis")

    def render_queue() -> None:
        queue_box.clear(); activity_box.clear()
        stages = [entry.get("stage", "Pronto para analisar") for entry in state["files"]]
        queued = sum(stage in {"Na fila", "Na fila para renderização"} for stage in stages)
        working = sum(stage in {"Extraindo áudio", "Normalizando áudio", "Detectando fala e transcrevendo", "Renderizando"} for stage in stages)
        ready = sum(stage in {"Cortes prontos", "Concluído"} for stage in stages)
        failed = sum(stage == "Falhou" for stage in stages)
        with queue_box:
            for label, value, color in (("na fila", queued, "text-slate-300"), ("trabalhando", working, "text-blue-300"), ("prontos", ready, "text-teal-300"), ("falhas", failed, "text-red-300")):
                with ui.card().classes("rc-queue flex-grow p-2"):
                    ui.label(str(value)).classes(f"text-lg font-bold {color}")
                    ui.label(label).classes("text-xs rc-muted")
        with activity_box:
            for event in state["events"][:5]:
                with ui.row().classes("rc-event w-full items-center gap-2 px-2 py-1"):
                    ui.label(event["time"]).classes("text-xs rc-muted")
                    ui.label(event["name"]).classes("text-xs flex-grow ellipsis")
                    ui.label(event["stage"]).classes("text-xs text-teal-200")

    def set_busy(value: bool) -> None:
        if value:
            analyze.disable(); process.disable(); parallelism.disable()
        else:
            analyze.enable(); process.enable(); parallelism.enable()

    def set_stage(entry: dict, stage: str, *, index: int | None = None, total: int | None = None, fraction: float = 0.0, error: str | None = None) -> None:
        entry["stage"] = stage
        entry["error"] = error
        entry["progress"] = round(100 * (entry.get("progress", 0) / 100 if error else fraction))
        state["events"].insert(0, {"time": datetime.now().strftime("%H:%M:%S"), "name": entry["name"], "stage": stage})
        del state["events"][12:]
        if index is not None and total:
            progress.value = min(1.0, ((index - 1) + fraction) / total)
        if stage in TERMINAL_STAGES:
            entry["completed_at"] = datetime.now().isoformat(timespec="seconds")
            persist_batch_summary()
        render_files()
        render_batch_summary()
        render_report()
        render_processing_center()
        if entry["path"] == state["selected"] and not entry.get("plan"):
            render_review()

    def select(entry: dict) -> None:
        state["selected"] = entry["path"]; state["active_cut"] = None; active_file.text = entry["name"]
        if entry.get("plan"):
            set_rules_controls(entry.get("rules", load_rules(entry["plan"].preset)))
        review_select.set_value(entry["path"] if entry.get("plan") else None)
        render_files(); render_review()

    def select_review(event) -> None:
        entry = next((candidate for candidate in state["files"] if candidate["path"] == event.value and candidate.get("plan")), None)
        if entry:
            select(entry)

    def refresh_review_selector() -> None:
        options = {entry["path"]: entry["name"] for entry in state["files"] if entry.get("plan")}
        review_select.set_options(options, value=state["selected"] if state["selected"] in options else None)
        review_select.set_visibility(bool(options))

    def toggle_cut(current: dict, index: int) -> None:
        disabled = current.setdefault("disabled_cuts", set())
        disabled.symmetric_difference_update({index}); render_review()

    def render_review() -> None:
        for box in (player_box, timeline_box, cuts_box, retakes_box, protected_box, transcript_box, result_box): box.clear()
        render_batch_summary()
        current = item()
        if not current or not current.get("plan"):
            stage = current.get("stage") if current else None
            with timeline_box:
                if stage and stage != "Pronto para analisar":
                    ui.spinner("dots", size="lg").classes("text-teal-300 m-5")
                    ui.label(stage).classes("text-sm font-bold")
                    ui.label(current.get("error") or "A revisão aparecerá assim que este vídeo terminar.").classes("rc-muted text-sm")
                else:
                    ui.label("Selecione um vídeo e execute a análise para montar a revisão.").classes("rc-muted text-sm p-12")
            return
        plan = current["plan"]; disabled = current.setdefault("disabled_cuts", set()); visible = reviewed_cuts(current)
        removed = sum(cut.end_s - cut.start_s for cut in visible); source_key = _key(current["path"]); MEDIA[source_key] = current["path"]
        preview_cuts = [[cut.start_s, cut.end_s] for cut in visible]
        with player_box:
            ReviewPreview(f"/media/{source_key}", preview_cuts).classes("w-full")
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
        state["operational_mode"] = None; set_processing_layout(False)
        render_files(); render_review()

    async def analyze_selected() -> None:
        targets = [entry for entry in state["files"] if entry["selected"]]
        if not targets or state["running"]: return
        state["running"] = True; progress.set_visibility(True); set_busy(True)
        state["operational_mode"] = None
        set_processing_layout(False)
        start_batch("análise", targets)
        for entry in targets:
            entry.update(stage="Na fila", error=None)
        render_files(); render_batch_summary(); render_report()
        completed: list[dict] = []
        failures = 0
        skipped = 0
        try:
            for index, entry in enumerate(targets, 1):
                step_count = 3 if normalize.value else 2
                try:
                    entry_started = perf_counter()
                    status.text = f"{index}/{len(targets)} · extraindo áudio: {entry['name']}"
                    set_stage(entry, "Extraindo áudio", index=index, total=len(targets), fraction=0.1)
                    await asyncio.sleep(0)
                    source = entry["path"]
                    if not await run.io_bound(has_audio_stream, source):
                        skipped += 1
                        set_stage(entry, "Sem áudio — ignorado", index=index, total=len(targets), fraction=1,
                                  error="Este vídeo não possui trilha de áudio para analisar.")
                        entry["analysis_elapsed_s"] = perf_counter() - entry_started
                        persist_batch_summary(); render_report()
                        status.text = f"{index}/{len(targets)} · ignorado sem áudio: {entry['name']}"
                        continue
                    if normalize.value:
                        audio_dir = Path(output.value) / ".audio"
                        extracted = await run.io_bound(extract_audio, entry["path"], audio_dir / f"{Path(entry['path']).stem}.m4a")
                        status.text = f"{index}/{len(targets)} · normalizando áudio: {entry['name']}"
                        set_stage(entry, "Normalizando áudio", index=index, total=len(targets), fraction=1 / step_count)
                        await asyncio.sleep(0)
                        source = await run.io_bound(normalize_loudness, extracted, audio_dir / f"{Path(entry['path']).stem}__lufs.m4a")
                    status.text = f"{index}/{len(targets)} · detectando fala e transcrevendo: {entry['name']}"
                    set_stage(entry, "Detectando fala e transcrevendo", index=index, total=len(targets), fraction=(step_count - 1) / step_count)
                    await asyncio.sleep(0)
                    plan, artifacts = await run.io_bound(analyze_clip, entry["path"], output.value, preset=preset.value, analysis_source=source)
                    entry.update(plan=plan, artifacts=artifacts, disabled_cuts=set(), rules=load_rules(preset.value))
                    entry["analysis_elapsed_s"] = perf_counter() - entry_started
                    set_stage(entry, "Cortes prontos", index=index, total=len(targets), fraction=1)
                    refresh_review_selector()
                    completed.append(entry)
                except Exception as exc:
                    failures += 1
                    entry["analysis_elapsed_s"] = perf_counter() - entry_started
                    status.text = f"{index}/{len(targets)} · falhou: {entry['name']}"
                    set_stage(entry, "Falhou", index=index, total=len(targets), fraction=1, error=_friendly_error(exc))
                await asyncio.sleep(0)
            if completed:
                select(completed[0])
            status.text = f"Análise concluída: {len(completed)}/{len(targets)} prontos" + (f" · {skipped} sem áudio" if skipped else "") + (f" · {failures} falharam" if failures else "")
        finally:
            state["running"] = False; progress.set_visibility(False); set_busy(False)

    async def process_selected() -> None:
        targets = [entry for entry in state["files"] if entry["selected"] and entry.get("plan")]
        if not targets or state["running"]: ui.notify("Analise ao menos um vídeo antes de processar.", type="warning"); return
        state["running"] = True; progress.set_visibility(True); set_busy(True)
        state["operational_mode"] = "render"
        set_processing_layout(True)
        start_batch("renderização", targets)
        for entry in targets:
            entry.update(stage="Na fila para renderização", error=None)
        render_files(); render_batch_summary(); persist_batch_summary(); render_report()
        completed = 0
        failures = 0
        finished = 0
        workers = int(parallelism.value)
        semaphore = asyncio.Semaphore(workers)

        async def render_entry(entry: dict) -> None:
            nonlocal completed, failures, finished
            async with semaphore:
                entry_started = perf_counter()
                try:
                    status.text = f"Renderizando em paralelo ({workers}) · {entry['name']}"
                    set_stage(entry, "Renderizando", fraction=0.1)
                    await asyncio.sleep(0)
                    disabled = entry.get("disabled_cuts", set())
                    reviewed = replace(entry["plan"], cuts=[cut for i, cut in enumerate(entry["plan"].cuts) if i not in disabled])
                    rendered, _ = await run.io_bound(render_with_handles, reviewed, output.value)
                    entry["rendered"] = str(rendered)
                    entry["render_elapsed_s"] = perf_counter() - entry_started
                    completed += 1
                    set_stage(entry, "Concluído", fraction=1)
                except Exception as exc:
                    failures += 1
                    entry["render_elapsed_s"] = perf_counter() - entry_started
                    status.text = f"Falhou · {entry['name']}"
                    set_stage(entry, "Falhou", fraction=1, error=_friendly_error(exc))
                finally:
                    finished += 1
                    progress.value = finished / len(targets)
                    render_processing_center()

        try:
            await asyncio.gather(*(render_entry(entry) for entry in targets))
            status.text = f"Render concluído: {completed}/{len(targets)} MP4s · {workers} em paralelo" + (f" · {failures} falharam" if failures else f" · saída em {output.value}")
        finally:
            state["running"] = False; progress.set_visibility(False); set_busy(False)

    async def browse_folder() -> None:
        chosen = await run.io_bound(choose_directory)
        if chosen: folder.value = chosen; await load_files()

    def refresh_live_batch() -> None:
        """Atualiza cronômetro, cartões e o arquivo do relatório sem esperar o próximo vídeo."""
        if state["running"] and state.get("batch"):
            persist_batch_summary()
            render_batch_summary()
            render_report()
            render_processing_center()

    def set_all(value: bool) -> None:
        for entry in state["files"]: entry["selected"] = value
        render_files()

    for control in (within, after, minimum, breath, crossfade, protect, punch): control.on_value_change(lambda _: refresh_plan())
    preset.on_value_change(lambda _: (render_rules(), refresh_plan()))
    review_select.on_value_change(select_review)
    browse.on_click(browse_folder); load.on_click(load_files); analyze.on_click(analyze_selected); process.on_click(process_selected)
    all_button.on_click(lambda: set_all(True)); none_button.on_click(lambda: set_all(False)); render_rules()
    ui.timer(1.0, refresh_live_batch)
