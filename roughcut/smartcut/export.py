from __future__ import annotations

import html
from pathlib import Path

from .schema import Cut, Word


def _overlaps_cut(word: Word, cuts: list[Cut]) -> bool:
    return any(word.start_s < cut.end_s and word.end_s > cut.start_s for cut in cuts)


def write_srt(words: list[Word], cuts: list[Cut], destination: str | Path) -> Path:
    """SRT de fala mantida, agrupada por frase e pronto para importar no Filmora."""
    kept = [word for word in words if not _overlaps_cut(word, cuts)]
    rows = []
    for index, word in enumerate(kept, 1):
        start = _srt_time(word.start_s)
        end = _srt_time(word.end_s)
        rows.append(f"{index}\n{start} --> {end}\n{word.text.strip()}\n")
    target = Path(destination)
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def write_review_report(cuts: list[Cut], retakes: list[dict], destination: str | Path) -> Path:
    lines = ["# Revisão de corte", "", f"## Cortes ({len(cuts)})", ""]
    for cut in cuts:
        lines.append(f"- `{cut.start_s:.2f}s–{cut.end_s:.2f}s` {cut.reason}: {cut.transcript_before} → {cut.transcript_after}")
    lines.extend(["", f"## Retakes ({len(retakes)})", ""])
    for take in retakes:
        lines.append(f"- `{take['start_s']:.2f}s–{take['end_s']:.2f}s` {take['text']} (mantém: {take['kept_text']})")
    target = Path(destination)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def write_fcpxml(source: str | Path, duration_s: float, cuts: list[Cut], destination: str | Path) -> Path:
    """FCPXML mínimo, apontando ao original; testar importação no Filmora manualmente."""
    source_path = Path(source).resolve().as_uri()
    segments = _keep_segments(duration_s, cuts)
    clips = "".join(
        f'<asset-clip ref="r1" offset="{_fcpx_time(offset)}" start="{_fcpx_time(start)}" duration="{_fcpx_time(end-start)}" name="{html.escape(Path(source).stem)}"/>'
        for offset, (start, end) in _timeline_offsets(segments)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<fcpxml version="1.10"><resources>'
        f'<format id="r0" frameDuration="1/30s" width="3840" height="2160"/>'
        f'<asset id="r1" src="{source_path}" start="0s" duration="{_fcpx_time(duration_s)}" hasVideo="1" hasAudio="1" format="r0"/>'
        '</resources><library><event name="roughcut"><project name="Corte inteligente"><sequence format="r0">'
        f'<spine>{clips}</spine></sequence></project></event></library></fcpxml>'
    )
    target = Path(destination)
    target.write_text(xml, encoding="utf-8")
    return target


def _keep_segments(duration_s: float, cuts: list[Cut]) -> list[tuple[float, float]]:
    cursor = 0.0
    segments = []
    for cut in sorted(cuts, key=lambda item: item.start_s):
        if cut.start_s > cursor:
            segments.append((cursor, cut.start_s))
        cursor = max(cursor, cut.end_s)
    if cursor < duration_s:
        segments.append((cursor, duration_s))
    return segments


def _timeline_offsets(segments: list[tuple[float, float]]):
    offset = 0.0
    for start, end in segments:
        yield offset, (start, end)
        offset += end - start


def _fcpx_time(seconds: float) -> str:
    return f"{round(seconds * 1000)}/1000s"


def _srt_time(seconds: float) -> str:
    millis = round(max(0, seconds) * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
