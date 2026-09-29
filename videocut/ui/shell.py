"""Moldura da aplicação: cabeçalho, etapas, conteúdo e atualização ao vivo."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from nicegui import ui

from . import theme
from .state import PAGES, Studio

Renderer = Callable[["Shell"], None]


class Shell:
    def __init__(self, studio: Studio, renderers: dict[int, Renderer]):
        self.studio = studio
        self.renderers = renderers
        self.live_hooks: list[Callable[[], None]] = []
        self.root: ui.element | None = None

    def go(self, page: int) -> None:
        self.studio.page = page
        self.refresh()
        with self.root:
            ui.run_javascript("window.scrollTo(0, 0)")

    def refresh(self) -> None:
        with self.root:
            self.nav.refresh()
            self.main.refresh()

    def notify(self, message: str, kind: str = "info") -> None:
        """Depois de um `await`, o botão que disparou a ação pode já ter sido recriado."""
        with self.root:
            ui.notify(message, type=kind, multi_line=True)

    def on_live(self, hook: Callable[[], None]) -> None:
        self.live_hooks.append(hook)

    def tick(self) -> None:
        for hook in list(self.live_hooks):
            hook()

    @ui.refreshable_method
    def nav(self) -> None:
        with ui.row().classes("w-full justify-between items-center"):
            project = self.studio.project
            theme.eyebrow(f"Projeto / {Path(project.folder).name}" if project else "Nenhum projeto aberto")
            ui.label(project.output_dir if project else "Whisper + Qwen3-VL locais · ffmpeg").classes("vc-tiny vc-muted")
        with ui.element("nav").classes("vc-nav"):
            for index, name in enumerate(PAGES):
                button = ui.button(f"{index + 1}  {name}", on_click=lambda _, i=index: self.go(i)).props("flat no-caps")
                if index == self.studio.page:
                    button.classes("active")
                if self.studio.busy and index != self.studio.page:
                    button.disable()

    @ui.refreshable_method
    def main(self) -> None:
        self.live_hooks.clear()
        self.renderers[self.studio.page](self)

    def build(self) -> None:
        theme.install()
        with ui.row().classes("vc-header w-full items-center gap-3 no-wrap"):
            ui.label("▤").classes("vc-mark")
            ui.label("VideoCut").classes("vc-brand")
            ui.label("/ montagem por conteúdo").classes("vc-muted gt-sm")
            ui.space()
            theme.pill("100% local · originais preservados")
        with ui.column().classes("vc-shell gap-0") as self.root:
            self.nav()
            self.main()
            with ui.element("footer").classes("vc-footer w-full"):
                theme.eyebrow("VideoCut v0.1")
                ui.label("Fatos com timestamp primeiro, interpretação editorial depois. Nada é enviado para fora do seu Mac.")
        ui.timer(0.5, self.tick)
