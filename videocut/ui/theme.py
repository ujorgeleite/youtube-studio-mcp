"""Linguagem visual do wireframe traduzida para NiceGUI: tokens, painéis e textos."""

from __future__ import annotations

from typing import Callable

from nicegui import ui

CSS = """
:root{--bg:#0c1218;--card:#151e28;--line:#2b3b4a;--muted:#a3b2c2;--mint:#75dfc6;--amber:#efc378;--blue:#9bbbe9;--red:#f2a7ad}
body{background:var(--bg);color:#eaf0f7;font:15px/1.5 Inter,system-ui,-apple-system,sans-serif}
.nicegui-content{padding:0;max-width:1450px;margin:auto}
.vc-header{background:#111923;border-bottom:1px solid var(--line);padding:16px 30px}
.vc-mark{border:1px solid #3d8274;border-radius:9px;width:36px;height:36px;display:grid;place-items:center;color:var(--mint);font-size:22px}
.vc-brand{font-size:21px;font-weight:750;letter-spacing:-.8px}
.vc-shell{padding:22px 32px 45px;width:100%}
.vc-muted{color:var(--muted)} .vc-tiny{font-size:12px} .vc-small{font-size:13px}
.vc-eyebrow{font-size:10px;letter-spacing:1.9px;font-weight:750;text-transform:uppercase;color:var(--mint)}
.vc-pill{display:inline-flex;align-items:center;padding:4px 9px;border:1px solid #3c515e;border-radius:5px;font-size:10px;letter-spacing:.9px;font-weight:650;color:#b7c9d8;white-space:nowrap;text-transform:uppercase}
.vc-pill.teal{background:#163d32;color:var(--mint);border-color:#316e5b}
.vc-pill.amber{color:var(--amber);background:#332a1c;border-color:#6e5833}
.vc-pill.red{color:var(--red);border-color:#71454d}
.vc-nav{display:flex;gap:6px;margin:18px 0 24px;width:100%}
.vc-nav .q-btn{flex:1;justify-content:flex-start;padding:10px 14px;border-radius:7px;color:var(--muted);background:#101922;border:1px solid var(--line)}
.vc-nav .q-btn.active{background:#1a3431;border-color:#4c9986;color:#a3f0db}
.vc-h1{font-size:32px;line-height:1.2;letter-spacing:-1px;margin:6px 0 8px;font-weight:650}
.vc-h2{font-size:21px;letter-spacing:-.4px;font-weight:650}
.vc-h3{font-size:16px;font-weight:650}
.vc-layout{display:grid;grid-template-columns:minmax(0,2.1fr) minmax(295px,1fr);gap:20px;width:100%;align-items:start}
.vc-stack{display:flex;flex-direction:column;gap:16px;min-width:0}
.vc-panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px}
.vc-panel.accent{background:linear-gradient(110deg,#19332f,#152029 85%);border-color:#498573}
.vc-panel.amber{background:#28251e;border-color:#6c5c40}
.vc-panel.report{background:#172e29;border-color:#356855}
.vc-note{font-size:12px;line-height:1.6;color:var(--muted);border-left:2px solid #4b6978;padding-left:12px;margin-top:14px}
.vc-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0;width:100%}
.vc-metric strong{display:block;font-size:30px;letter-spacing:-1px;font-weight:650;font-variant-numeric:tabular-nums}
.vc-metric span{font-size:11px;color:var(--muted)}
.vc-btn{border:1px solid var(--line)!important;border-radius:8px!important;background:#111c26!important;color:#eaf0f7!important}
.vc-btn.primary{background:var(--mint)!important;color:#09251e!important;border-color:var(--mint)!important;font-weight:750}
.vc-btn.small{font-size:12px;padding:2px 8px;min-height:28px}
.vc-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;width:100%}
.vc-take{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--card)}
.vc-take.checked{border-color:#408d78}
.vc-thumb{aspect-ratio:16/9;background:#1e3340;position:relative;overflow:hidden;width:100%}
.vc-thumb img{width:100%;height:100%;object-fit:cover}
.vc-duration{position:absolute;bottom:8px;right:8px;background:#0c151de6;font:11px monospace;padding:3px 5px;border-radius:4px}
.vc-progress{height:7px;border-radius:4px;background:#26343f;overflow:hidden;width:100%;margin:12px 0}
.vc-progress>div{height:100%;background:var(--mint);transition:width .3s}
.vc-clock{font-size:clamp(38px,6vw,70px);letter-spacing:-3px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.3}
.vc-stage{padding:12px 0;border-top:1px solid var(--line);display:flex;gap:12px;align-items:center;width:100%}
.vc-circle{border:1px solid #426256;color:var(--mint);border-radius:50%;width:25px;height:25px;display:grid;place-items:center;font-size:12px}
.vc-console{border-left:2px solid #45836f;padding:7px 12px;background:#111c24;margin-top:6px;font-size:12px;width:100%}
.vc-check-row{display:flex;gap:12px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--line);width:100%}
.vc-evidence{border:1px solid var(--line);padding:12px 14px;border-radius:8px;background:#111b24;display:flex;gap:12px;align-items:center;margin-top:10px;width:100%}
.vc-filetag{background:#263947;border:1px solid #3d5567;padding:4px 7px;border-radius:4px;font:11px monospace;color:#bdd3df}
.vc-flow{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12px;color:#b8dfd1}
.vc-flow span.step{border:1px solid #34534f;border-radius:5px;padding:5px 8px;background:#142b28}
.vc-beat{border:1px solid var(--line);border-radius:9px;padding:12px;background:#172330;width:100%}
.vc-beat.selected{border-color:var(--mint);background:#1b3431}
.vc-beat.excluded{opacity:.52}
.vc-track{display:flex;gap:4px;width:100%;margin:8px 0 14px}
.vc-block{background:#254f46;border:1px solid #396c60;border-radius:5px;min-width:20px;height:42px;overflow:hidden;padding:6px;color:#ceebdf;font-size:11px;cursor:pointer}
.vc-block.audio{background:#293e5e;border-color:#4b6792;color:#d1ddf1;cursor:default}
.vc-block.broll{background:#63512a;border-color:#8a713e;color:#f3e0b3;cursor:default}
.vc-block.gap{background:transparent;border:1px dashed #33434f;cursor:default}
.vc-footer{display:flex;align-items:center;gap:20px;border-top:1px solid var(--line);margin-top:30px;padding-top:18px;color:var(--muted);font-size:11px}
.vc-field .q-field__control{background:#111c26;border-radius:8px}
.vc-field .q-field__label,.vc-field .q-field__native,.vc-field .q-field__input{color:#eaf0f7}
.q-checkbox__inner{color:var(--mint)}
.warn{color:var(--amber)} .check{color:var(--mint)} .bad{color:var(--red)}
@media(max-width:1000px){.vc-layout{grid-template-columns:1fr}.vc-shell{padding:18px}}
@media(max-width:650px){.vc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.vc-nav{flex-wrap:wrap}.vc-metrics{gap:8px}.vc-h1{font-size:26px}}
"""


def install() -> None:
    ui.add_css(CSS)
    ui.colors(primary="#75dfc6", secondary="#9bbbe9", accent="#efc378", positive="#75dfc6", negative="#f2a7ad", warning="#efc378")
    ui.dark_mode(True)


def text(value: str, classes: str = "") -> ui.label:
    return ui.label(value).classes(classes)


def eyebrow(value: str) -> ui.label:
    return text(value, "vc-eyebrow")


def pill(value: str, tone: str = "") -> ui.label:
    return text(value, f"vc-pill {tone}")


def note(value: str) -> ui.label:
    return text(value, "vc-note")


def title(step: str, heading: str, detail: str) -> None:
    with ui.column().classes("gap-0 w-full mb-5"):
        eyebrow(step)
        text(heading, "vc-h1")
        text(detail, "vc-muted")


def panel(tone: str = "") -> ui.element:
    return ui.element("section").classes(f"vc-panel {tone} w-full")


def layout() -> ui.element:
    return ui.element("div").classes("vc-layout")


def stack() -> ui.element:
    return ui.element("div").classes("vc-stack")


def metric(value: str, label: str) -> None:
    with ui.element("div").classes("vc-metric"):
        ui.html(f"<strong>{value}</strong>")
        ui.label(label).classes("vc-tiny vc-muted")


def button(label: str, on_click: Callable | None = None, *, primary: bool = False, small: bool = False) -> ui.button:
    classes = "vc-btn" + (" primary" if primary else "") + (" small" if small else "")
    return ui.button(label, on_click=on_click, color=None).props("unelevated no-caps").classes(classes)


def progress_bar(fraction: float) -> None:
    ui.html(f'<div class="vc-progress"><div style="width:{max(0.0, min(1.0, fraction)) * 100:.1f}%"></div></div>').classes("w-full")
