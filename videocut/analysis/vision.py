"""Análise visual em duas passagens: leitura ampla do take e detalhe onde vale a pena."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.cache import StageCache, fingerprint
from core.config import sampling
from core.schema import Take, Transcript, VisualObservation
from core.serial import from_data
from media.frames import broad_sample_times, extract_frames, merge_times, scene_changes, spread_times

from .vlm import LocalModel, ModelError, generate_json

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
SEVERE_ISSUES = {"tela_preta", "obstruido"}
Progress = Callable[[float, str], None]


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@dataclass
class Window:
    start_s: float
    end_s: float
    times: list[float]


def thin(times: list[float], limit: int) -> list[float]:
    if len(times) <= limit:
        return times
    step = len(times) / limit
    return [times[int(index * step)] for index in range(limit)]


def sample_plan(duration_s: float, scenes: list[float], settings: dict) -> list[float]:
    base = broad_sample_times(duration_s, settings.get("broad_every_s", 12), maximum=settings.get("broad_max_frames", 24))
    inside = [moment + 0.4 for moment in scenes if 0.5 < moment < duration_s - 0.5]
    return thin(merge_times(base, inside), settings.get("broad_max_frames", 24))


def windows_for(times: list[float], duration_s: float, per_call: int) -> list[Window]:
    chunks = [times[index:index + per_call] for index in range(0, len(times), per_call)]
    windows = []
    for position, chunk in enumerate(chunks):
        start = 0.0 if position == 0 else (chunks[position - 1][-1] + chunk[0]) / 2
        end = duration_s if position == len(chunks) - 1 else (chunk[-1] + chunks[position + 1][0]) / 2
        windows.append(Window(round(start, 3), round(end, 3), chunk))
    return windows


def _text(value: object) -> str:
    return str(value).strip() if value not in (None, [], {}) else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, list) else []


def _interest(value: object) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def observation_from(data: dict, take_id: str, start_s: float, end_s: float, *, detail: bool = False) -> VisualObservation:
    return VisualObservation(
        take_id=take_id,
        start_s=round(start_s, 3),
        end_s=round(end_s, 3),
        description=_text(data.get("descricao")),
        action=_text(data.get("acao")),
        setting=_text(data.get("ambiente")),
        shot=_text(data.get("plano")),
        subjects=_strings(data.get("pessoas")),
        issues=[issue.lower() for issue in _strings(data.get("problemas"))],
        interest=_interest(data.get("interesse")),
        usable_as_broll=bool(data.get("apoio")),
        detail_pass=detail,
    )


def detail_candidates(observations: list[VisualObservation], transcript: Transcript | None, limit: int) -> list[int]:
    """Prioriza ação sem fala e trechos ambíguos; ignora frames inutilizáveis."""
    scored = []
    for index, item in enumerate(observations):
        if SEVERE_ISSUES & set(item.issues):
            continue
        silent = not (transcript and transcript.text_between(item.start_s, item.end_s))
        ambiguous = not item.description or 0.35 <= item.interest <= 0.6
        score = item.interest + (0.3 if item.action and silent else 0) + (0.2 if ambiguous else 0)
        if item.interest >= 0.65 or ambiguous or (item.action and silent):
            scored.append((score, index))
    return sorted(index for _, index in sorted(scored, reverse=True)[:limit])


def refine_bounds(data: dict, times: list[float], start_s: float, end_s: float) -> tuple[float, float]:
    try:
        first = int(data.get("inicio_frame", 1))
        last = int(data.get("fim_frame", len(times)))
    except (TypeError, ValueError):
        return start_s, end_s
    if not 1 <= first <= last <= len(times):
        return start_s, end_s
    return (start_s if first == 1 else times[first - 1]), (end_s if last == len(times) else times[last - 1])


def _speech(transcript: Transcript | None, start_s: float, end_s: float) -> str:
    return transcript.text_between(start_s, end_s)[:600] if transcript else ""


def vision_variant(model_name: str) -> str:
    """Muda com o modelo, os prompts e a amostragem: só então a descrição é refeita."""
    return fingerprint(model_name, load_prompt("visao_ampla"), load_prompt("visao_detalhe"), sorted(sampling().items()))


def analyze_take_vision(
    take: Take,
    transcript: Transcript | None,
    model: LocalModel,
    cache_root: str | Path,
    frames_dir: str | Path,
    *,
    progress: Progress | None = None,
    refresh: bool = False,
) -> list[VisualObservation]:
    settings = sampling()
    broad_prompt, detail_prompt = load_prompt("visao_ampla"), load_prompt("visao_detalhe")
    cache = StageCache(cache_root, take.path)
    variant = vision_variant(model.name)
    cached = None if refresh else cache.load("vision", variant)
    if cached is not None:
        return [from_data(VisualObservation, item) for item in cached]
    report = progress or (lambda fraction, message: None)

    scenes = cache.load("scenes")
    if scenes is None:
        scenes = scene_changes(take.analysis_path)
        cache.save("scenes", scenes)
    times = sample_plan(take.duration_s, scenes, settings)
    frames = dict(extract_frames(take.analysis_path, times, Path(frames_dir) / take.id, "ampla"))
    windows = windows_for(times, take.duration_s, settings.get("frames_per_call", 4))
    detail_limit = settings.get("detail_windows_per_take", 4)
    total_steps = len(windows) + detail_limit

    observations: list[VisualObservation] = []
    failures = 0
    for step, window in enumerate(windows, start=1):
        report(step / total_steps, f"Descrevendo {take.id} · trecho {step}/{len(windows)}")
        prompt = broad_prompt.format(
            instantes=", ".join(f"{moment:.1f}s" for moment in window.times),
            arquivo=take.name, fala=_speech(transcript, window.start_s, window.end_s),
        )
        try:
            data = generate_json(model, prompt, [frames[moment] for moment in window.times])
        except ModelError:
            failures += 1
            continue
        if isinstance(data, dict):
            observations.append(observation_from(data, take.id, window.start_s, window.end_s))
    if windows and failures == len(windows):
        raise ModelError(f"o modelo visual não descreveu nenhum trecho de {take.name}")

    chosen = detail_candidates(observations, transcript, detail_limit)
    per_window = settings.get("detail_frames_per_window", 6)
    for position, index in enumerate(chosen, start=1):
        report((len(windows) + position) / total_steps, f"Detalhando {take.id} · momento {position}/{len(chosen)}")
        broad = observations[index]
        sequence = spread_times(broad.start_s, broad.end_s, per_window)
        images = [path for _, path in extract_frames(take.analysis_path, sequence, Path(frames_dir) / take.id, "detalhe")]
        prompt = detail_prompt.format(
            instantes=", ".join(f"{moment:.1f}s" for moment in sequence), arquivo=take.name,
            fala=_speech(transcript, broad.start_s, broad.end_s), anterior=broad.description, total=len(sequence),
        )
        try:
            data = generate_json(model, prompt, images)
        except ModelError:
            continue
        if isinstance(data, dict):
            start, end = refine_bounds(data, sequence, broad.start_s, broad.end_s)
            observations[index] = observation_from(data, take.id, start, end, detail=True)

    report(1.0, f"{take.id} descrito")
    cache.save("vision", observations, variant)
    return observations
