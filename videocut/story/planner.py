"""Planejador editorial em etapas: capítulos primeiro, depois os blocos de cada capítulo.

Pedir a montagem inteira numa resposta só não escala: um vídeo longo precisa de
dezenas de blocos e modelos locais devolvem listas curtas. Aqui cada resposta é
pequena, a base cronológica (`chronology.py`) garante que nada útil some por
omissão do modelo, e o validador continua sendo o filtro de fatos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from analysis.vlm import LocalModel, ModelError, generate_json
from core.cache import fingerprint
from core import settings
from core.config import load_yaml
from core.extensions import skills_text
from core.schema import SPEECH, Inventory, Moment, StoryReport
from core.serial import read_json, write_json
from core.timefmt import clock, span

from .adjust import shorten
from .chronology import BaseCut, base_cut, chronological, moment_block, recorded_at
from .coherence import SceneRules, tidy
from .validate import build_report

SPEECH_CHARS = 220
CHAPTERS_MAX_TOKENS = 1500
CHAPTER_MAX_TOKENS = 2200
LONG_SPEECH_S = 8.0
UNDERFILLED_RATIO = 0.5
Progress = Callable[[str], None]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def moment_line(moment: Moment) -> str:
    parts = [moment.id, span(moment.start_s, moment.end_s), moment.kind]
    if moment.speech:
        parts.append(f"fala: “{_clip(moment.speech, SPEECH_CHARS)}”")
    if moment.visual:
        parts.append(f"imagem: {_clip(moment.visual, 150)}")
    parts.append(f"interesse {moment.interest:.1f}")
    return " | ".join(parts)


def channel_context() -> dict[str, str]:
    channel = load_yaml("canal.yaml")
    return {
        "canal": f"{channel.get('canal', '')}. {channel.get('publico', '')}".strip(". "),
        "regras": "\n".join(f"- {rule}" for rule in channel.get("regras", [])),
        "formatos": channel.get("formatos", {}),
    }


def takes_overview(inventory: Inventory, cut: BaseCut) -> str:
    lines = []
    for take in chronological(inventory.takes):
        speech = [moment for moment in cut.speech if moment.take_id == take.id]
        visual = next((moment.visual for moment in inventory.moments if moment.take_id == take.id and moment.visual), "")
        moment = recorded_at(take)
        parts = [take.id, moment.strftime("%H:%M") if moment else "--:--", clock(take.duration_s)]
        if speech:
            parts.append(f"fala: “{_clip(' '.join(item.speech for item in speech), 160)}”")
            parts.append("gancho possível: " + ", ".join(item.id for item in speech[:3]))
        else:
            parts.append("sem fala útil")
        if visual:
            parts.append(f"imagem: {_clip(visual, 110)}")
        lines.append(" | ".join(parts))
    return "\n".join(lines) or "(nenhum take)"


def ask(model: LocalModel, prompt: str, cache_dir: Path, name: str, max_tokens: int, refresh: bool) -> Any:
    """Cada resposta fica em cache pelo modelo e pelo texto exato do pedido."""
    cache = cache_dir / f"{name}__{fingerprint(model.name, prompt)}.json"
    raw = None if refresh else read_json(cache)
    if raw is None:
        raw = generate_json(model, prompt, max_tokens=max_tokens)
        write_json(cache, raw)
    return raw


def fallback_chapters(inventory: Inventory, size: int = 6) -> list[dict]:
    ordered = chronological(inventory.takes)
    return [{"titulo": f"Parte {index // size + 1}", "papel": "desenvolvimento", "takes": [take.id for take in ordered[index:index + size]]}
            for index in range(0, len(ordered), size)]


def normalize_chapters(raw: dict, inventory: Inventory) -> list[dict]:
    """Cada take em exatamente um capítulo, na ordem do dia; takes esquecidos vão para o capítulo vizinho."""
    order = {take.id: index for index, take in enumerate(chronological(inventory.takes))}
    chapters, seen = [], set()
    for item in raw.get("capitulos") or [] if isinstance(raw, dict) else []:
        if not isinstance(item, dict):
            continue
        takes = [take for take in item.get("takes") or [] if take in order and take not in seen]
        if takes:
            seen.update(takes)
            chapters.append({"titulo": str(item.get("titulo") or "Capítulo").strip(), "papel": str(item.get("papel") or "desenvolvimento"),
                             "takes": sorted(takes, key=order.get)})
    if not chapters:
        return fallback_chapters(inventory)
    chapters.sort(key=lambda chapter: order[chapter["takes"][0]])
    for take_id in sorted(set(order) - seen, key=order.get):
        earlier = [chapter for chapter in chapters if order[chapter["takes"][0]] < order[take_id]]
        target = earlier[-1] if earlier else chapters[0]
        target["takes"] = sorted([*target["takes"], take_id], key=order.get)
    return chapters


def chapter_moments(cut: BaseCut, takes: list[str]) -> list[Moment]:
    wanted = set(takes)
    pool = {moment.id: moment for moment in [*cut.speech, *cut.broll] if moment.take_id in wanted}
    return sorted(pool.values(), key=lambda moment: (cut.order[moment.take_id], moment.start_s))


def chapter_blocks(raw: Any, moments: list[Moment], cut: BaseCut) -> list[dict]:
    """Aceita o que o modelo escolheu; fala útil que ele só esqueceu volta para a sequência."""
    by_id = {moment.id: moment for moment in moments}
    speech_ids = {moment.id for moment in cut.speech}
    broll_ids = {moment.id for moment in cut.broll}
    blocks: list[dict] = []
    used: set[str] = set()
    discarded = {str(item) for item in (raw.get("descartados") or [] if isinstance(raw, dict) else [])}
    for item in raw.get("blocos") or [] if isinstance(raw, dict) else []:
        moment = by_id.get(str(item.get("momento", ""))) if isinstance(item, dict) else None
        if moment is None or moment.id in used:
            continue
        used.add(moment.id)
        block = moment_block(moment, str(item.get("papel") or "desenvolvimento"), str(item.get("titulo") or ""), str(item.get("motivo") or ""))
        overlays = [overlay for overlay in item.get("apoio") or [] if overlay in broll_ids and overlay in by_id and overlay not in used]
        used.update(overlays)
        block["apoio"] = [{"momento": overlay} for overlay in overlays]
        blocks.append(block)
    for moment in moments:
        if moment.id in speech_ids and moment.id not in used and moment.id not in discarded:
            blocks.append(moment_block(moment, reason="Fala mantida da base cronológica"))
            used.add(moment.id)
    blocks.sort(key=lambda block: (cut.order[by_id[block["momento"]].take_id], by_id[block["momento"]].start_s))
    fill_broll(blocks, moments, by_id, used)
    return blocks


def fill_broll(blocks: list[dict], moments: list[Moment], by_id: dict[str, Moment], used: set[str]) -> None:
    """Falas longas sem imagem de apoio recebem o próximo momento de ação livre do capítulo."""
    free = [moment for moment in moments if moment.kind != SPEECH and moment.id not in used]
    for block in blocks:
        moment = by_id[block["momento"]]
        if moment.kind != SPEECH or moment.duration_s < LONG_SPEECH_S or block.get("apoio") or not free:
            continue
        candidate = next((item for item in free if item.take_id != moment.take_id), free[0])
        free.remove(candidate)
        block["apoio"] = [{"momento": candidate.id}]


def outline_values(inventory: Inventory, cut: BaseCut, intention: str = "", format_key: str = "auto",
                   target_minutes: float | None = None, skills: list[str] | None = None) -> dict[str, str]:
    context = channel_context()
    return {
        "canal": context["canal"], "regras": context["regras"], "skills": skills_text(skills or [], "capitulos"),
        "intencao": intention.strip() or "não informada — descubra as possibilidades do material",
        "formato": context["formatos"].get(format_key, format_key or context["formatos"].get("auto", "")),
        "duracao": f"cerca de {target_minutes:g} minutos" if target_minutes else "livre, a que o material sustentar",
        "takes": takes_overview(inventory, cut),
    }


def outline_prompt(inventory: Inventory, cut: BaseCut, intention: str = "", format_key: str = "auto",
                   target_minutes: float | None = None, skills: list[str] | None = None) -> str:
    return settings.read("capitulos").format(**outline_values(inventory, cut, intention, format_key, target_minutes, skills))


def chapter_values(video: str, chapter: dict, number: int, total: int, moments: list[Moment], target_s: float | None,
                   skills: list[str] | None = None) -> dict[str, object]:
    return {
        "video": video, "numero": number, "total": total, "capitulo": chapter["titulo"], "papel": chapter["papel"],
        "duracao": clock(target_s) if target_s else "a que o material sustentar",
        "regras": channel_context()["regras"].replace("\n", " "), "skills": skills_text(skills or [], "capitulo"),
        "momentos": "\n".join(moment_line(moment) for moment in moments),
    }


def chapter_prompt(video: str, chapter: dict, number: int, total: int, moments: list[Moment], target_s: float | None,
                   skills: list[str] | None = None) -> str:
    return settings.read("capitulo").format(**chapter_values(video, chapter, number, total, moments, target_s, skills))


def plan_chapter(model: LocalModel, cache_dir: Path, video: str, chapter: dict, number: int, total: int,
                 moments: list[Moment], cut: BaseCut, target_s: float | None, refresh: bool, skills: list[str]) -> list[dict]:
    if not moments:
        return []
    prompt = chapter_prompt(video, chapter, number, total, moments, target_s, skills)
    try:
        raw = ask(model, prompt, cache_dir, f"capitulo{number:02d}", CHAPTER_MAX_TOKENS, refresh)
    except ModelError:
        raw = {}
    return chapter_blocks(raw, moments, cut)


def plan_stories(
    inventory: Inventory,
    model: LocalModel,
    cache_dir: str | Path,
    *,
    intention: str = "",
    format_key: str = "auto",
    target_minutes: float | None = None,
    refresh: bool = False,
    progress: Progress | None = None,
    skills: list[str] | None = None,
) -> StoryReport:
    report_step = progress or (lambda message: None)
    cache = Path(cache_dir)
    active = list(skills or [])
    cut = base_cut(inventory)
    moments = {moment.id: moment for moment in inventory.moments}
    target_s = target_minutes * 60 if target_minutes else None

    report_step("Dividindo o material em capítulos")
    prompt = outline_prompt(inventory, cut, intention, format_key, target_minutes, active)
    try:
        outline = ask(model, prompt, cache, "capitulos", CHAPTERS_MAX_TOKENS, refresh)
    except ModelError:
        outline = {}
    outline = outline if isinstance(outline, dict) else {}
    chapters = normalize_chapters(outline, inventory)
    title = str(outline.get("titulo") or "Vídeo").strip()

    speech_total = cut.speech_s or 1.0
    chapter_results: list[list[dict]] = []
    for number, chapter in enumerate(chapters, start=1):
        report_step(f"Planejando capítulo {number}/{len(chapters)} · {chapter['titulo']}")
        pool = chapter_moments(cut, chapter["takes"])
        share = sum(moment.duration_s for moment in pool if moment.kind == SPEECH) / speech_total
        chapter_results.append(plan_chapter(model, cache, title, chapter, number, len(chapters), pool, cut,
                                            target_s * share if target_s else None, refresh, active))

    hook = moments.get(str(outline.get("gancho") or ""))
    report_step("Montando e validando a sequência")
    raw = assemble(outline, chapters, chapter_results, hook, title)
    report = build_report(raw, inventory, None)
    rules = SceneRules.load()
    for proposal in report.proposals:
        for video in proposal.videos:
            proposal.warnings.extend(tidy(video, inventory, rules))
    fit_duration(report, inventory, target_s, cut)
    return report


def assemble(outline: dict, chapters: list[dict], results: list[list[dict]], hook: Moment | None, title: str) -> dict:
    blocks = [block for chapter in results for block in chapter]
    if hook is not None and hook.kind == SPEECH:
        blocks = [block for block in blocks if block["momento"] != hook.id]
        blocks.insert(0, moment_block(hook, "gancho", "Abertura", "Momento forte escolhido para abrir o vídeo"))
    if blocks and blocks[-1]["papel"] not in ("conclusao", "mensagem"):
        blocks[-1]["papel"] = "conclusao"
    gaps = [gap for gap in outline.get("lacunas") or [] if isinstance(gap, dict)]
    proposals = [{"titulo": title, "resumo": str(outline.get("resumo") or ""), "recomendada": True,
                  "videos": [{"titulo": title, "mensagem": str(outline.get("mensagem") or ""), "blocos": blocks}], "lacunas": gaps}]
    groups = [group for group in outline.get("dividir") or [] if isinstance(group, list)]
    videos = []
    for group in groups:
        indexes = [index for index in group if isinstance(index, int) and 0 <= index < len(chapters)]
        chosen = [block for index in indexes for block in results[index]]
        if indexes and chosen:
            videos.append({"titulo": " · ".join(chapters[index]["titulo"] for index in indexes), "blocos": chosen})
    if len(videos) > 1:
        proposals.append({"titulo": "Dividir em vídeos independentes", "resumo": "Um vídeo por assunto, seguindo os capítulos.",
                          "videos": videos})
    return {"veredito": outline.get("veredito"), "resumo": outline.get("resumo"), "temas": outline.get("temas"),
            "intencao": outline.get("intencao"), "propostas": proposals}


def fit_duration(report: StoryReport, inventory: Inventory, target_s: float | None, cut: BaseCut) -> None:
    """Só o vídeo principal segue a duração pedida: acima dela encurta sem modelo; muito abaixo, avisa."""
    main = next((proposal for proposal in report.proposals if not proposal.multiple), None)
    if not target_s or main is None:
        return
    for index, video in enumerate(main.videos):
        if video.duration_s > target_s * 1.1:
            main.videos[index] = shorten(video, target_s, inventory)
        elif video.duration_s < target_s * UNDERFILLED_RATIO:
            main.warnings.append(
                f"“{video.title}” tem {clock(video.duration_s)}, menos da metade dos {clock(target_s)} pedidos. "
                f"O material tem {clock(cut.speech_s)} de fala aproveitável; o resto foi descartado como repetido ou fraco."
            )
