from __future__ import annotations

import os
import sys

from nicegui import ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui import silence  # noqa: E402,F401


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Remoção de silêncios", port=8080, reload=False, show=True)
