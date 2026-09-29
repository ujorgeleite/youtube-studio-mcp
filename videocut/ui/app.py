from __future__ import annotations

import sys
from pathlib import Path

from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import analysis_view, material, media, review, stories  # noqa: E402,F401
from ui.preview import install_player  # noqa: E402
from ui.shell import Shell  # noqa: E402
from ui.state import ANALYSIS, DELIVERY, MATERIAL, REVIEW, STORIES, STUDIO  # noqa: E402

PORT = 8090


def placeholder(step: str) -> callable:
    def render(shell: Shell) -> None:
        ui.label(f"{step}: em construção").classes("vc-muted")
    return render


RENDERERS = {
    MATERIAL: material.render,
    ANALYSIS: analysis_view.render,
    STORIES: stories.render,
    REVIEW: review.render,
    DELIVERY: placeholder("Entrega"),
}


@ui.page("/")
def index() -> None:
    STUDIO.restore_last()
    install_player()
    Shell(STUDIO, RENDERERS).build()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="VideoCut", port=PORT, reload=False, show=True, dark=True)
