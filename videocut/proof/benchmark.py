"""Mede modelos visuais no seu material: tempo, memória, falhas de JSON e descrições."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable

from analysis.vision import analyze_take_vision
from analysis.vlm import LocalModel, MlxModel
from core.config import vision_options
from core.schema import Take, Transcript, VisualObservation
from core.timefmt import clock


@dataclass
class CountingModel:
    """Envolve o modelo real contando chamadas e respostas sem JSON."""

    inner: LocalModel
    calls: int = 0
    invalid: int = 0

    @property
    def name(self) -> str:
        return self.inner.name

    def generate(self, prompt: str, images=None, max_tokens: int = 700) -> str:
        from analysis.jsontext import JsonTextError, parse_json

        self.calls += 1
        text = self.inner.generate(prompt, images, max_tokens)
        try:
            parse_json(text)
        except JsonTextError:
            self.invalid += 1
        return text

    def release(self) -> None:
        self.inner.release()


@dataclass
class ModelRun:
    key: str
    repo: str
    load_s: float = 0.0
    seconds: dict[str, float] = field(default_factory=dict)
    observations: dict[str, list[VisualObservation]] = field(default_factory=dict)
    calls: int = 0
    invalid: int = 0
    peak_gb: float = 0.0
    error: str | None = None

    @property
    def material_s(self) -> float:
        return sum(self.seconds.values())


def peak_memory_gb() -> float:
    try:
        import mlx.core as mx
        return mx.get_peak_memory() / 1e9
    except (ImportError, AttributeError):
        return 0.0


def reset_peak_memory() -> None:
    try:
        import mlx.core as mx
        mx.reset_peak_memory()
    except (ImportError, AttributeError):
        pass


def benchmark(
    takes: list[Take],
    transcripts: dict[str, Transcript],
    work_dir: str | Path,
    keys: list[str] | None = None,
    model_factory: Callable[[str], LocalModel] = MlxModel,
) -> list[ModelRun]:
    """Cada modelo roda com cache próprio e isolado, para medir inferência real."""
    options = vision_options()
    runs = []
    for key in keys or list(options):
        run = ModelRun(key, options[key]["repo"])
        reset_peak_memory()
        model = CountingModel(model_factory(run.repo))
        try:
            started = perf_counter()
            model.inner.generate("Responda apenas {}.", None, 8)
            run.load_s = perf_counter() - started
            for take in takes:
                started = perf_counter()
                run.observations[take.id] = analyze_take_vision(
                    take, transcripts.get(take.id), model, Path(work_dir) / "cache" / key, Path(work_dir) / "frames", refresh=True,
                )
                run.seconds[take.id] = perf_counter() - started
        except Exception as error:  # noqa: BLE001 - um modelo que falha não impede medir o outro
            run.error = str(error).splitlines()[0][:200]
        finally:
            run.calls, run.invalid, run.peak_gb = model.calls, model.invalid, peak_memory_gb()
            model.release()
        runs.append(run)
    return runs


def benchmark_report(runs: list[ModelRun], takes: list[Take]) -> str:
    material = sum(take.duration_s for take in takes)
    lines = [
        "# Benchmark de modelos visuais", "",
        f"{len(takes)} takes · {clock(material)} de material. Cache desligado: cada modelo analisa tudo de novo.", "",
        "| Modelo | Carga | Análise | Tempo por minuto de vídeo | Memória de pico | Chamadas | JSON inválido |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in runs:
        per_minute = run.material_s / (material / 60) if material else 0
        lines.append(f"| {run.key} | {run.load_s:.0f} s | {clock(run.material_s)} | {per_minute:.0f} s | "
                     f"{run.peak_gb:.1f} GB | {run.calls} | {run.invalid} |" + (f" erro: {run.error}" if run.error else ""))
    lines += ["", "## Descrições lado a lado", ""]
    for take in takes:
        lines += [f"### {take.id} · {take.name}", ""]
        for run in runs:
            lines.append(f"**{run.key}**")
            for item in sorted(run.observations.get(take.id, []), key=lambda obs: obs.start_s)[:6]:
                detail = f" · ação: {item.action}" if item.action else ""
                issues = f" · problemas: {', '.join(item.issues)}" if item.issues else ""
                lines.append(f"- {clock(item.start_s)}–{clock(item.end_s)} · {item.description}{detail}{issues} · interesse {item.interest:.1f}")
            lines.append("")
    lines += ["Compare com o que você sabe dos takes: o modelo que erra menos fatos vale mais que o mais rápido.", ""]
    return "\n".join(lines)
