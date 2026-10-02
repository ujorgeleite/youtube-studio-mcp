"""Selo de “Mac acordado” e checklist do seletor “Rodar de madrugada”."""

from __future__ import annotations

import os
from time import monotonic

from nicegui import run, ui

from core.keepawake import KEEP_AWAKE
from core.power import CheckItem, on_ac_power, open_settings, power_checklist

from . import theme

MARKS = {"ok": ("✓", "check"), "pendente": ("◷", "warn"), "lembrete": ("·", "vc-muted")}
AC_CACHE_S = 30.0
_ac_cache: dict[str, float | bool | None] = {"at": -AC_CACHE_S, "value": None}


def ac_power() -> bool | None:
    """O selo é redesenhado a cada meio segundo; a fonte de energia é relida a cada 30 s."""
    if monotonic() - float(_ac_cache["at"]) >= AC_CACHE_S:
        _ac_cache.update(at=monotonic(), value=on_ac_power())
    return _ac_cache["value"]  # type: ignore[return-value]


def awake_badge(project) -> None:
    with ui.row().classes("items-center gap-2 mt-1"):
        if KEEP_AWAKE.active:
            theme.pill("Madrugada · Mac mantido acordado" if project.overnight else "Mac mantido acordado", "teal")
        if ac_power() is False:
            ui.label("Na bateria: ligue na tomada para rodar por horas.").classes("vc-tiny warn")


def checklist(items: list[CheckItem]) -> None:
    for item in items:
        mark, tone = MARKS[item.status]
        with ui.element("div").classes("vc-check-row"):
            ui.label(mark).classes(tone).style("font-size:16px")
            with ui.column().classes("gap-0 flex-grow"):
                ui.label(item.label).classes("vc-small").style("font-weight:650")
                ui.label(item.detail).classes("vc-tiny vc-muted")
            if item.settings and item.ok is not True:
                theme.button("Abrir Ajustes", lambda _, url=item.settings: run.io_bound(open_settings, url), small=True)


def overnight_checklist() -> list[CheckItem]:
    items = power_checklist(os.getpid())
    checklist(items)
    return items
