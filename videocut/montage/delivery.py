"""Pacote de entrega por vídeo: MP4, plano JSON, relatório, legenda e timeline."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Callable

from core.project import ReviewState
from core.schema import EditPlan, Inventory, Proposal, StoryVideo
from core.serial import write_json

from .plan import build_edit_plan, ordered_beats
from .render import render_plan
from .report import editorial_report, write_report
from .subtitles import write_srt
from .timeline import write_xmeml

Progress = Callable[[float, str], None]


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:60] or "video"


def artifact_paths(root: Path, video: StoryVideo) -> dict[str, Path]:
    slug = slugify(video.title)
    return {
        "video": root / "videos" / f"{slug}__montagem.mp4",
        "plan": root / "plans" / f"{slug}__plano.json",
        "report": root / "reports" / f"{slug}__relatorio.md",
        "subtitles": root / "subtitles" / f"{slug}.srt",
        "timeline": root / "timelines" / f"{slug}__timeline.xml",
    }


def write_documents(proposal: Proposal, video: StoryVideo, plan: EditPlan, inventory: Inventory,
                    review: ReviewState | None, paths: dict[str, Path]) -> None:
    beats = ordered_beats(video, review)
    write_json(paths["plan"], {
        "proposal": {"id": proposal.id, "title": proposal.title, "partial": proposal.partial},
        "video": {"id": video.id, "title": video.title, "message": video.message},
        "beats": beats,
        "excluded": [beat.id for beat in video.beats if beat not in beats],
        "edit_plan": plan,
    })
    write_report(editorial_report(proposal, video, plan, inventory, review), paths["report"])
    write_srt(plan, inventory.transcripts, paths["subtitles"])
    write_xmeml(plan, inventory.takes, paths["timeline"])


def deliver(
    proposal: Proposal,
    video: StoryVideo,
    inventory: Inventory,
    review: ReviewState | None,
    root: str | Path,
    work_dir: str | Path,
    *,
    progress: Progress | None = None,
    before_segment: Callable[[], None] | None = None,
) -> dict[str, str]:
    """Documentos primeiro: se o render falhar, plano e timeline já estão disponíveis."""
    report = progress or (lambda fraction, message: None)
    paths = artifact_paths(Path(root), video)
    plan = build_edit_plan(proposal.id, video, inventory.takes, review)
    report(0.02, "Gravando plano, relatório, legenda e timeline")
    write_documents(proposal, video, plan, inventory, review, paths)
    render_plan(plan, paths["video"], work_dir, progress=lambda fraction, message: report(0.05 + fraction * 0.95, message),
                before_segment=before_segment)
    return {key: str(path) for key, path in paths.items()}
