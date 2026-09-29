"""Fontes de prévia: proxy da câmera, original compatível ou proxy H.264 gerado sob demanda."""

from __future__ import annotations

import json
from pathlib import Path

from nicegui import run, ui

from core.project import Layout
from core.schema import Beat, Take
from media.audio import make_proxy
from media.probe import probe

from .media import media_url

BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}
PLAYER_JS = Path(__file__).with_name("player.js")


def install_player() -> None:
    ui.add_body_html(f"<script>{PLAYER_JS.read_text(encoding='utf-8')}</script>")


async def preview_path(take: Take, layout: Layout) -> str:
    if take.proxy:
        return take.proxy
    info = await run.io_bound(probe, take.path)
    if info.video_codec in BROWSER_CODECS:
        return take.path
    return str(await run.io_bound(make_proxy, take.path, layout.proxies / f"{take.id}.mp4"))


def player(prefix: str = "vc", height: str = "340px") -> None:
    ui.html(
        f'<div style="position:relative;width:100%;height:{height};background:#0c161f;border-radius:10px;overflow:hidden">'
        f'<video id="{prefix}-main" controls playsinline style="width:100%;height:100%;object-fit:contain"></video>'
        f'<video id="{prefix}-over" muted playsinline style="display:none;position:absolute;inset:0;width:100%;height:100%;'
        'object-fit:contain;background:#0c161f;pointer-events:none"></video></div>'
    ).classes("w-full")


async def play(beats: list[Beat], takes: dict[str, Take], layout: Layout, prefix: str = "vc") -> None:
    items = []
    for beat in beats:
        take = takes.get(beat.take_id)
        if take is None:
            continue
        overlays = []
        for number, overlay in enumerate(beat.overlays):
            source = takes.get(overlay.take_id)
            if source:
                overlays.append({"key": f"{beat.id}-{number}", "src": media_url(await preview_path(source, layout)),
                                 "start": overlay.start_s, "end": overlay.end_s, "at": overlay.at_s})
        items.append({"src": media_url(await preview_path(take, layout)), "start": beat.start_s, "end": beat.end_s, "overlays": overlays})
    ui.run_javascript(f"window.vcSequence('{prefix}-main', '{prefix}-over', {json.dumps(items)})")
