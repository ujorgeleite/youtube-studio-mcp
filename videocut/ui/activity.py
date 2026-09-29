"""Indicador de atividade: toda ação demorada mostra o que faz, há quanto tempo e quanto falta."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from nicegui import ui

from core.timefmt import stopwatch

DONE_VISIBLE_S = 3.0


@dataclass
class ActivityState:
    label: str = ""
    detail: str = ""
    fraction: float | None = None
    started: float = 0.0
    finished: float = 0.0
    error: str | None = None

    def start(self, label: str) -> None:
        self.label, self.detail, self.fraction, self.error = label, "", None, None
        self.started, self.finished = perf_counter(), 0.0

    @property
    def running(self) -> bool:
        return bool(self.started) and not self.finished

    @property
    def visible(self) -> bool:
        return self.running or (bool(self.finished) and perf_counter() - self.finished < DONE_VISIBLE_S)

    @property
    def elapsed_s(self) -> float:
        return ((self.finished or perf_counter()) - self.started) if self.started else 0.0


class Activity:
    """Usado com `with shell.activity("Carregando pasta") as step:`; `step(...)` pode ser chamado de threads."""

    def __init__(self, state: ActivityState, label: str, refresh):
        self.state = state
        self.label = label
        self.refresh = refresh

    def __call__(self, detail: str, fraction: float | None = None) -> None:
        self.state.detail = detail
        self.state.fraction = fraction

    def __enter__(self) -> "Activity":
        self.state.start(self.label)
        self.refresh()
        return self

    def __exit__(self, kind, error, trace) -> bool:
        self.state.finished = perf_counter()
        if error is not None:
            self.state.error = str(error).strip().splitlines()[0][:180] if str(error).strip() else type(error).__name__
        self.refresh()
        return False


def seconds(value: float) -> str:
    return f"{value:.1f} s".replace(".", ",") if value < 60 else stopwatch(value)


def render(state: ActivityState) -> None:
    """Cartão fixo no canto inferior; vive fora do conteúdo que as telas recriam."""
    if not state.visible:
        return
    tone = "#71454d" if state.error else "#316e5b" if state.finished else "#498573"
    with ui.element("div").classes("vc-activity").style(f"border-color:{tone}"):
        with ui.row().classes("items-center gap-3 no-wrap w-full"):
            if state.running:
                ui.spinner("dots", size="lg", color="teal-3")
            else:
                ui.label("✗" if state.error else "✓").classes("bad" if state.error else "check").style("font-size:22px")
            with ui.column().classes("gap-0 flex-grow").style("min-width:0"):
                title = state.label if state.running else (f"{state.label}: falhou" if state.error else f"{state.label} · concluído")
                ui.label(title).classes("vc-small").style("font-weight:650")
                detail = state.error or state.detail
                if detail:
                    ui.label(detail).classes("vc-tiny vc-muted").style("overflow:hidden;text-overflow:ellipsis;white-space:nowrap")
            ui.label(seconds(state.elapsed_s)).classes("vc-small").style("font-variant-numeric:tabular-nums;white-space:nowrap")
        if state.running:
            if state.fraction is None:
                ui.linear_progress(show_value=False).props("indeterminate color=teal-3 size=4px").classes("mt-2")
            else:
                ui.linear_progress(value=state.fraction, show_value=False).props("color=teal-3 size=4px instant-feedback").classes("mt-2")
