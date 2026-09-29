from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.offline import enable_offline  # noqa: E402

enable_offline()

from nicegui import ui  # noqa: E402

from ui import analysis_view, delivery_view, material, media, review, stories  # noqa: E402,F401
from ui.preview import install_player  # noqa: E402
from ui.shell import Shell  # noqa: E402
from ui.state import ANALYSIS, DELIVERY, MATERIAL, REVIEW, STORIES, STUDIO  # noqa: E402

PORT = int(os.environ.get("VIDEOCUT_PORT", "8090"))

RENDERERS = {
    MATERIAL: material.render,
    ANALYSIS: analysis_view.render,
    STORIES: stories.render,
    REVIEW: review.render,
    DELIVERY: delivery_view.render,
}


@ui.page("/")
def index() -> None:
    STUDIO.restore_last()
    install_player()
    Shell(STUDIO, RENDERERS).build()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="VideoCut", port=PORT, reload=False, show=os.environ.get("VIDEOCUT_OPEN_BROWSER", "1") != "0", dark=True)
