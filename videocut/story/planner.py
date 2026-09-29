"""Planejador editorial: um pedido ao modelo local, validado deterministicamente."""

from __future__ import annotations

from pathlib import Path

from analysis.vlm import LocalModel, generate_json
from core.cache import fingerprint
from core.config import load_yaml
from core.schema import ACTION, BROLL, PROBLEM, SPEECH, Inventory, Moment, StoryReport
from core.serial import read_json, write_json
from core.timefmt import clock, span

from .validate import build_report

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "historias.md"
MAX_MOMENTS = 240
SPEECH_CHARS = 260
PLANNER_MAX_TOKENS = 4500


def _moment_line(moment: Moment) -> str:
    parts = [moment.id, span(moment.start_s, moment.end_s), moment.kind]
    if moment.speech:
        text = moment.speech if len(moment.speech) <= SPEECH_CHARS else moment.speech[:SPEECH_CHARS].rsplit(" ", 1)[0] + "…"
        parts.append(f"fala: “{text}”")
    if moment.visual:
        parts.append(f"imagem: {moment.visual[:180]}")
    parts.append(f"interesse {moment.interest:.1f}")
    if moment.issues:
        parts.append("problemas: " + ", ".join(moment.issues))
    return " | ".join(parts)


def select_moments(moments: list[Moment], limit: int = MAX_MOMENTS) -> list[Moment]:
    """Toda fala entra; ação e apoio entram por interesse; problemas só se sobrar espaço."""
    speech = [moment for moment in moments if moment.kind == SPEECH]
    visual = sorted((moment for moment in moments if moment.kind in (ACTION, BROLL)), key=lambda moment: -moment.interest)
    problems = [moment for moment in moments if moment.kind == PROBLEM]
    chosen = (speech + visual + problems)[:limit]
    keep = {moment.id for moment in chosen}
    return [moment for moment in moments if moment.id in keep]


def render_inventory(inventory: Inventory, limit: int = MAX_MOMENTS) -> str:
    chosen = select_moments(inventory.moments, limit)
    lines = []
    for take in inventory.takes:
        items = [moment for moment in chosen if moment.take_id == take.id]
        if not items:
            continue
        lines.append(f"### {take.id} · {take.name} · {clock(take.duration_s)}")
        lines.extend(_moment_line(moment) for moment in items)
    if len(chosen) < len(inventory.moments):
        lines.append(f"({len(inventory.moments) - len(chosen)} momentos de baixo interesse omitidos)")
    return "\n".join(lines) or "(nenhum momento analisado)"


def build_prompt(inventory: Inventory, intention: str = "", format_key: str = "auto", target_minutes: float | None = None) -> str:
    channel = load_yaml("canal.yaml")
    formats = channel.get("formatos", {})
    return PROMPT.read_text(encoding="utf-8").format(
        canal=f"{channel.get('canal', '')}. {channel.get('publico', '')}".strip(". "),
        regras="\n".join(f"- {rule}" for rule in channel.get("regras", [])),
        intencao=intention.strip() or "não informada — descubra as possibilidades do material",
        formato=formats.get(format_key, format_key or formats.get("auto", "")),
        duracao=f"cerca de {target_minutes:g} minutos" if target_minutes else "livre, a que o material sustentar",
        inventario=render_inventory(inventory),
    )


def plan_stories(
    inventory: Inventory,
    model: LocalModel,
    cache_dir: str | Path,
    *,
    intention: str = "",
    format_key: str = "auto",
    target_minutes: float | None = None,
    refresh: bool = False,
) -> StoryReport:
    prompt = build_prompt(inventory, intention, format_key, target_minutes)
    cache = Path(cache_dir) / f"historias__{fingerprint(model.name, prompt)}.json"
    raw = None if refresh else read_json(cache)
    if raw is None:
        raw = generate_json(model, prompt, max_tokens=PLANNER_MAX_TOKENS)
        write_json(cache, raw)
    return build_report(raw, inventory, target_minutes * 60 if target_minutes else None)
