"""Prévia dos prompts com o texto do editor e os dados reais do projeto aberto, sem chamar o modelo."""

from __future__ import annotations

from analysis.vision import sample_plan, windows_for
from core import settings
from core.config import sampling
from story.chronology import base_cut
from story.planner import chapter_moments, chapter_values, normalize_chapters, outline_values

NO_PROJECT = "Abra um projeto já analisado para ver a prévia com os dados reais dele."


def build_preview(studio, key: str, text: str) -> str:
    item = settings.editable(key)
    if item.kind == settings.YAML:
        return text
    project, inventory = studio.project, studio.inventory
    if project is None or inventory is None:
        return NO_PROJECT
    cut = base_cut(inventory)
    if key == "capitulos":
        return text.format(**outline_values(inventory, cut, project.intention, project.format, project.target_minutes, project.skills))
    if key == "capitulo":
        chapters = normalize_chapters({}, inventory)
        chapter = chapters[0]
        return text.format(**chapter_values("Título do vídeo", chapter, 1, len(chapters), chapter_moments(cut, chapter["takes"]),
                                            None, project.skills))
    return vision_preview(inventory, text)


def vision_preview(inventory, text: str) -> str:
    take = next((item for item in inventory.takes if inventory.transcripts.get(item.id)), inventory.takes[0] if inventory.takes else None)
    if take is None:
        return NO_PROJECT
    settings_sampling = sampling()
    times = sample_plan(take.duration_s, [], settings_sampling)
    window = windows_for(times, take.duration_s, settings_sampling.get("frames_per_call", 4))[0]
    transcript = inventory.transcripts.get(take.id)
    observation = next((item for item in inventory.observations if item.take_id == take.id), None)
    values = {
        "instantes": ", ".join(f"{moment:.1f}s" for moment in window.times),
        "arquivo": take.name,
        "fala": transcript.text_between(window.start_s, window.end_s)[:600] if transcript else "",
        "anterior": observation.description if observation else "",
        "total": len(window.times),
    }
    return text.format(**{name: values.get(name, "") for name in settings.placeholders(text)})
