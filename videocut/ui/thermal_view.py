"""Temperatura ao vivo e aviso de pausa para esfriar."""

from __future__ import annotations

from nicegui import ui

from core.thermal import ThermalGovernor
from core.timefmt import stopwatch

from . import theme


def render(governor: ThermalGovernor | None) -> None:
    if governor is None:
        return
    reading = governor.last
    mode = "cargas longas ligado" if governor.enabled else "sem pausas automáticas"
    with ui.row().classes("items-center gap-2 mt-2"):
        theme.pill(f"🌡 {reading.label}", "amber" if governor.too_hot(reading) else "")
        ui.label(mode).classes("vc-tiny vc-muted")
    if governor.paused_since is not None:
        limits = governor.config
        with theme.panel("amber").classes("mt-3"):
            theme.pill("Esfriando o Mac", "amber")
            ui.label(f"Pausado há {stopwatch(governor.paused_for_s)} · {reading.label}").classes("vc-h3 mt-2")
            ui.label(f"Retoma quando ficar em até {limits.resume_temp_c:g} °C e no máximo “razoável”. "
                     f"Nova leitura a cada {limits.poll_s:g} s; espera no máximo {limits.max_wait_min:g} min.").classes("vc-small vc-muted")
    elif governor.pauses:
        ui.label(governor.summary()).classes("vc-tiny vc-muted")
    if governor.warning:
        ui.label(governor.warning).classes("vc-tiny warn")
