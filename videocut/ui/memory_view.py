"""Memória do Mac na interface: indicador, apps que ocupam e passo a passo para liberar."""

from __future__ import annotations

from time import monotonic

from nicegui import run, ui

from core.memory import MemoryStatus, freeing_steps, gb_text, memory_status, open_activity_monitor, required_gb

from . import theme

FULL_CACHE_S = 15.0
QUICK_CACHE_S = 5.0
LEVEL_TEXT = {"ok": ("Memória suficiente", "teal"), "apertado": ("Memória apertada", "amber"), "critico": ("Memória insuficiente", "red")}
_cache: dict[str, tuple[float, MemoryStatus] | None] = {"full": None, "quick": None}


def cached_status(with_apps: bool = True, force: bool = False) -> MemoryStatus:
    """A lista de apps leva ~1 s (usa `top`); a leitura rápida só `vm_stat` e `sysctl`."""
    key, ttl = ("full", FULL_CACHE_S) if with_apps else ("quick", QUICK_CACHE_S)
    entry = _cache[key]
    if force or entry is None or monotonic() - entry[0] >= ttl:
        _cache[key] = (monotonic(), memory_status(with_apps=with_apps))
    return _cache[key][1]  # type: ignore[index]


def bar(status: MemoryStatus) -> None:
    used = status.used_fraction * 100
    color = "#f2a7ad" if used >= 90 else "#efc378" if used >= 75 else "#75dfc6"
    ui.html(f'<div class="vc-progress"><div style="width:{used:.1f}%;background:{color}"></div></div>').classes("w-full")


def summary_line(status: MemoryStatus) -> str:
    return (f"Livre {gb_text(status.available_gb)} de {gb_text(status.total_gb)} · swap {gb_text(status.swap_gb)} · "
            f"pressão {status.pressure_label}")


def live_line(model_key: str | None) -> None:
    status = cached_status(with_apps=False)
    label, tone = LEVEL_TEXT[status.level(required_gb(model_key))]
    with ui.row().classes("items-center gap-2 mt-1"):
        theme.pill(f"🧠 {label}", tone)
        ui.label(summary_line(status)).classes("vc-tiny vc-muted")


def steps_list(status: MemoryStatus, needed: float) -> None:
    for number, step in enumerate(freeing_steps(status, needed), start=1):
        ui.label(f"{number}. {step}").classes("vc-small").style("margin-top:6px")


def apps_list(status: MemoryStatus) -> None:
    top = status.apps[0].gb if status.apps else 1
    for app in status.apps[:6]:
        with ui.row().classes("w-full items-center no-wrap gap-2 mt-1"):
            ui.label(app.name).classes("vc-small").style("width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap")
            ui.html(f'<div class="vc-progress" style="margin:0"><div style="width:{app.gb / top * 100:.0f}%;background:#9bbbe9"></div></div>').classes("flex-grow")
            ui.label(gb_text(app.gb)).classes("vc-tiny").style("width:62px;text-align:right;font-variant-numeric:tabular-nums")


def memory_panel(shell, model_key: str | None) -> None:
    status = cached_status()
    needed = required_gb(model_key)
    label, tone = LEVEL_TEXT[status.level(needed)]

    def refresh() -> None:
        cached_status(force=True)
        shell.main.refresh()

    with theme.panel():
        with ui.row().classes("w-full items-center"):
            ui.label("Memória do Mac").classes("vc-h3")
            ui.space()
            theme.pill(label, tone)
        bar(status)
        ui.label(summary_line(status)).classes("vc-tiny vc-muted")
        ui.label(f"O modelo escolhido precisa de ~{needed:g} GB livres para rodar sem swap.").classes("vc-tiny vc-muted")
        ui.label("Quem está usando").classes("vc-small mt-3").style("font-weight:650")
        apps_list(status)
        with ui.expansion("Como liberar memória", value=status.level(needed) != "ok").classes("w-full mt-2 vc-small"):
            steps_list(status, needed)
        with ui.row().classes("gap-2 mt-3"):
            theme.button("Atualizar", refresh, small=True)
            theme.button("Abrir Monitor de Atividade", lambda: run.io_bound(open_activity_monitor), small=True)


async def confirm_low_memory(shell, model_key: str | None) -> bool:
    status = await run.io_bound(cached_status, True, True)
    needed = required_gb(model_key)
    if status.level(needed) == "ok":
        return True
    with shell.root, ui.dialog() as dialog, theme.panel("amber").style("width:min(620px,calc(100vw - 35px));max-height:85vh;overflow:auto"):
        theme.pill(LEVEL_TEXT[status.level(needed)][0], "amber")
        ui.label("Pouca memória livre para a análise").classes("vc-h2 mt-2")
        ui.label(f"{summary_line(status)}. Com pouca memória o macOS usa o disco e a análise pode levar o dobro do tempo.").classes("vc-muted")
        apps_list(status)
        ui.label("Como liberar").classes("vc-h3 mt-3")
        steps_list(status, needed)
        with ui.row().classes("gap-3 mt-4"):
            theme.button("Analisar assim mesmo", lambda: dialog.submit(True))
            theme.button("Vou liberar memória primeiro", lambda: dialog.submit(False), primary=True)
    return bool(await dialog)
