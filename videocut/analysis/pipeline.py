"""Orquestra a análise do projeto respeitando a memória: um modelo pesado por vez.

Ordem: áudio de todos os takes → Whisper em todos → libera Whisper → modelo
visual descreve todos → o mesmo modelo planeja as histórias → libera.
Falhas ficam no take; o restante do lote continua.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable

from core.config import models, vision_repo
from core.project import (
    STAGE_FAILED, STAGE_MEDIA, STAGE_PENDING, STAGE_READY, STAGE_SPEECH, STAGE_VISION, Project, TakeStatus,
)
from core.schema import Inventory, StoryReport, Take, Transcript, VisualObservation
from core.thermal import ThermalGovernor
from core.serial import from_data, read_json, write_json
from media.audio import extract_speech_audio
from media.probe import MediaError, probe
from story.planner import plan_stories

from .inventory import build_inventory
from .models import ensure_model
from .speech import release_model, transcribe_take
from .vision import analyze_take_vision
from .vlm import LocalModel, MlxModel, ThermalGuardedModel

STAGES = (
    "Preparar modelos, mídia e áudio",
    "Transcrever e localizar falas",
    "Descrever cenas e ações",
    "Conectar temas e avaliar histórias",
)
ModelFactory = Callable[[str], LocalModel]


class AnalysisCancelled(RuntimeError):
    pass


@dataclass
class AnalysisMonitor:
    """Estado ao vivo lido pela interface a cada tique do timer."""

    stage: int = -1
    message: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    log: list[str] = field(default_factory=list)
    error: str | None = None
    download: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    thermal: ThermalGovernor | None = None

    @property
    def elapsed_s(self) -> float:
        if not self.started_at:
            return 0.0
        return (self.finished_at or perf_counter()) - self.started_at

    def note(self, text: str) -> None:
        self.log.append(text)
        del self.log[:-40]


def speech_source(take: Take) -> str:
    """Áudio do proxy da câmera quando existir; senão, do original."""
    if take.proxy:
        try:
            if probe(take.proxy).has_audio:
                return take.proxy
        except MediaError:
            pass
    return take.path


def inventory_path(project: Project) -> Path:
    return project.layout.analysis / "inventario.json"


def load_inventory(project: Project) -> Inventory | None:
    data = read_json(inventory_path(project))
    return from_data(Inventory, data) if data is not None else None


class Analysis:
    def __init__(self, project: Project, monitor: AnalysisMonitor | None = None,
                 model_factory: ModelFactory = MlxModel, refresh: bool = False,
                 governor: ThermalGovernor | None = None):
        self.project = project
        self.monitor = monitor or AnalysisMonitor()
        self.model_factory = model_factory
        self.refresh = refresh
        self.failed: dict[str, str] = {}
        self.governor = governor or ThermalGovernor(enabled=project.long_run, cancel=self.monitor.cancel)
        self.monitor.thermal = self.governor

    def set_status(self, take: Take, stage: str, fraction: float = 0.0, error: str | None = None) -> None:
        current = self.project.status.get(take.id) or TakeStatus()
        self.project.status[take.id] = TakeStatus(stage, round(fraction, 3), error, current.seconds)

    def fail(self, take: Take, error: Exception) -> None:
        message = str(error).strip().splitlines()[0][:200] if str(error).strip() else type(error).__name__
        self.failed[take.id] = message
        self.set_status(take, STAGE_FAILED, error=message)
        self.monitor.note(f"{take.id} · falhou: {message}")

    def check_cancel(self) -> None:
        if self.monitor.cancel.is_set():
            raise AnalysisCancelled("análise cancelada")

    def enter(self, stage: int) -> None:
        self.monitor.stage = stage
        self.monitor.message = STAGES[stage]

    def active(self, takes: list[Take]) -> list[Take]:
        return [take for take in takes if take.id not in self.failed]

    def ensure_models(self, takes: list[Take], vision: str) -> None:
        """Baixa antes de processar: falta de rede aparece no início, não no meio do lote."""
        self.enter(0)

        def progress(fraction: float, message: str) -> None:
            self.monitor.message = message
            self.monitor.download = fraction

        if any(take.has_audio for take in takes):
            ensure_model(models().get("whisper", "mlx-community/whisper-large-v3-turbo"), "modelo de fala (Whisper)", progress)
        ensure_model(vision, "modelo visual (Qwen3-VL)", progress)
        self.monitor.download = None

    def prepare_audio(self, takes: list[Take]) -> dict[str, Path]:
        self.enter(0)
        audio: dict[str, Path] = {}
        for take in takes:
            self.check_cancel()
            self.set_status(take, STAGE_MEDIA, 0.1)
            if not take.has_audio:
                self.monitor.note(f"{take.id} · sem trilha de áudio; só imagem")
                continue
            try:
                audio[take.id] = extract_speech_audio(speech_source(take), self.project.layout.audio / f"{take.id}.wav")
            except MediaError as error:
                self.fail(take, error)
        return audio

    def transcribe(self, takes: list[Take], audio: dict[str, Path]) -> dict[str, Transcript]:
        self.enter(1)
        transcripts: dict[str, Transcript] = {}
        try:
            for take in self.active(takes):
                if take.id not in audio:
                    continue
                self.governor.wait_if_hot()
                self.check_cancel()
                self.set_status(take, STAGE_SPEECH, 0.3)
                self.monitor.message = f"Transcrevendo {take.id} · {take.name}"
                try:
                    transcripts[take.id] = transcribe_take(take.id, take.path, audio[take.id], self.project.layout.cache, refresh=self.refresh)
                except Exception as error:  # noqa: BLE001 - qualquer falha do Whisper fica restrita ao take
                    self.fail(take, error)
                    continue
                for sentence in transcripts[take.id].sentences[:2]:
                    self.monitor.note(f"{take.id} · fala / {sentence.text[:90]}")
        finally:
            release_model()
        return transcripts

    def describe(self, takes: list[Take], transcripts: dict[str, Transcript], model: LocalModel) -> dict[str, list[VisualObservation]]:
        loading = self.monitor.message
        self.enter(2)
        self.monitor.message = loading
        observations: dict[str, list[VisualObservation]] = {}
        for take in self.active(takes):
            self.check_cancel()
            started = perf_counter()

            def progress(fraction: float, message: str, take: Take = take) -> None:
                self.set_status(take, STAGE_VISION, 0.4 + fraction * 0.6)
                self.monitor.message = message

            try:
                observations[take.id] = analyze_take_vision(
                    take, transcripts.get(take.id), model, self.project.layout.cache, self.project.layout.frames,
                    progress=progress, refresh=self.refresh,
                )
            except Exception as error:  # noqa: BLE001 - erro do modelo ou do ffmpeg não interrompe o lote
                self.fail(take, error)
                continue
            self.set_status(take, STAGE_READY, 1.0)
            self.project.status[take.id].seconds = round(perf_counter() - started, 1)
            self.project.save()
            for item in sorted(observations[take.id], key=lambda item: -item.interest)[:2]:
                self.monitor.note(f"{take.id} · imagem / {(item.action or item.description)[:90]}")
        return observations

    def run(self) -> StoryReport:
        project = self.project
        takes = project.selected_takes
        if not takes:
            raise ValueError("nenhum take selecionado")
        self.monitor.started_at = perf_counter()
        self.monitor.finished_at = 0.0
        for take in takes:
            self.set_status(take, STAGE_PENDING)
        model: LocalModel | None = None
        try:
            repo = vision_repo(project.model or None)
            self.ensure_models(takes, repo)
            self.check_cancel()
            audio = self.prepare_audio(takes)
            transcripts = self.transcribe(takes, audio)
            project.save()
            self.monitor.message = "Carregando o modelo visual na memória…"
            model = ThermalGuardedModel(self.model_factory(repo), self.governor)
            observations = self.describe(takes, transcripts, model)
            project.save()
            self.check_cancel()
            if not self.active(takes):
                raise RuntimeError("nenhum take pôde ser analisado")
            self.enter(3)
            inventory = build_inventory(takes, transcripts, observations, self.failed)
            write_json(inventory_path(project), inventory)
            report = plan_stories(
                inventory, model, project.layout.analysis, intention=project.intention,
                format_key=project.format, target_minutes=project.target_minutes, refresh=self.refresh,
            )
            write_json(project.layout.analysis / "historias.json", report)
            project.report = report
            project.chosen = None
            project.review = {}
            project.save()
            self.monitor.note(f"{len(report.proposals)} proposta(s) · veredito: {report.verdict.replace('_', ' ')}")
            return report
        except Exception as error:
            self.monitor.error = str(error)
            project.save()
            raise
        finally:
            if model is not None:
                model.release()
            for line in (self.governor.summary(), self.governor.warning):
                if line:
                    self.monitor.note(line)
            self.monitor.finished_at = perf_counter()
