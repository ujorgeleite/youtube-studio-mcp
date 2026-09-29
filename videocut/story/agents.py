"""Agentes: etapas extras que leem a montagem escolhida e devolvem texto para você revisar."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from analysis.vlm import LocalModel
from core.extensions import Extension
from core.project import ReviewState
from core.safety import write_text
from core.schema import StoryVideo
from core.settings import placeholders
from core.timefmt import clock
from montage.plan import ordered_beats

from .planner import channel_context

AGENT_VARIABLES = ("canal", "titulo", "mensagem", "intencao", "duracao", "sequencia", "capitulos")
OUTER_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.DOTALL)
AGENT_MAX_TOKENS = 1500


def chapter_marks(video: StoryVideo, review: ReviewState | None) -> str:
    """Capítulos do YouTube calculados pela montagem, não pelo modelo: começam em 00:00."""
    marks, cursor, current = [], 0.0, None
    for beat in ordered_beats(video, review):
        name = beat.chapter or "Vídeo"
        if name != current:
            marks.append(f"{clock(cursor)} {name}")
            current = name
        cursor += beat.duration_s
    return "\n".join(marks) or "00:00 Vídeo"


def sequence_text(video: StoryVideo, review: ReviewState | None) -> str:
    """Blocos numerados com o tempo no vídeo final, na ordem da revisão."""
    lines, cursor = [], 0.0
    for number, beat in enumerate(ordered_beats(video, review), start=1):
        evidence = beat.evidence[0] if beat.evidence else None
        content = (evidence.quote or f"[imagem] {evidence.observation}") if evidence else beat.title
        lines.append(f"{number:02d} · {clock(cursor)} · {beat.role} · {content[:220]}")
        cursor += beat.duration_s
    return "\n".join(lines)


class _Missing(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def agent_prompt(agent: Extension, video: StoryVideo, review: ReviewState | None, intention: str) -> str:
    values = {
        "canal": channel_context()["canal"],
        "titulo": video.title,
        "mensagem": video.message or "não definida",
        "intencao": intention or "não informada",
        "duracao": clock(sum(beat.duration_s for beat in ordered_beats(video, review))),
        "sequencia": sequence_text(video, review),
        "capitulos": chapter_marks(video, review),
    }
    return agent.body.format_map(_Missing(values))


def unknown_variables(body: str) -> list[str]:
    return sorted(placeholders(body) - set(AGENT_VARIABLES))


def run_agent(agent: Extension, model: LocalModel, video: StoryVideo, review: ReviewState | None, intention: str,
              folder: str | Path) -> Path:
    answer = model.generate(agent_prompt(agent, video, review, intention), None, AGENT_MAX_TOKENS).strip()
    fenced = OUTER_FENCE.match(answer)
    answer = fenced.group(1).strip() if fenced else answer
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# {agent.name}\n\n_{video.title} · gerado em {stamp} pelo modelo {model.name}_\n\n"
    return write_text(Path(folder) / f"{agent.key}__{video.id}.md", header + answer + "\n")


def results(folder: str | Path, video_id: str) -> list[Path]:
    root = Path(folder)
    return sorted(root.glob(f"*__{video_id}.md")) if root.is_dir() else []

