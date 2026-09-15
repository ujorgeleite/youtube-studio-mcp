"""Passo 3 — assemble: concatena uma cut-list em um único MP4 (o "stringout").

Determinístico: dado o mesmo cut-list e os mesmos clipes, produz o mesmo vídeo.
Não depende de LLM nem de Whisper. É o passo que ancora o schema do cut-list.

Schema do cut-list (produzido pelo passo 2):

    {
      "roughcut": [
        {
          "beat": "cold_open",
          "clips": [ {"clip_id": "C01", "in": "00:00:03", "out": "00:00:08"} ],
          "broll_suggestion": "..."
        },
        {
          "beat": "broll_slot",
          "clips": [],
          "broll_suggestion": "drone sobre a cidade"
        }
      ]
    }

Beats com `clips` vazio são slots de B-roll: viram um slug de 1s (preto com o texto
da sugestão) para o usuário ver no editor onde entra cada B-roll.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

VIDEO_W = 1280
VIDEO_H = 720
FPS = 30
SAMPLE_RATE = 44100
BROLL_SLUG_SECONDS = 1

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
)


class AssembleError(RuntimeError):
    pass


@dataclass
class _Segment:
    beat: str
    kind: str  # "clip" | "broll"
    seconds: float


def parse_timecode(tc: str) -> float:
    """HH:MM:SS(.mmm) -> segundos. Aceita também MM:SS e SS."""
    parts = str(tc).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise AssembleError(f"timecode inválido: {tc!r}")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def _ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise AssembleError(
            "ffmpeg não encontrado no PATH. Instale-o (ex: brew install ffmpeg)."
        )


def _find_font() -> str | None:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _normalized_video_opts() -> list[str]:
    return [
        "-vf",
        f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "2",
        "-pix_fmt",
        "yuv420p",
    ]


def _cut_clip(src: str, start: float, duration: float, dest: str) -> None:
    if duration <= 0:
        raise AssembleError(f"duração não positiva ({duration}s) para {src}")
    proc = _ffmpeg(
        [
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            src,
            *_normalized_video_opts(),
            dest,
        ]
    )
    if proc.returncode != 0 or not os.path.exists(dest):
        raise AssembleError(f"falha ao cortar {src}: {proc.stderr.strip()}")


def _make_broll_slug(label: str, dest: str, workdir: str) -> None:
    """Slug de 1s: preto com o texto da sugestão de B-roll (fallback sem texto)."""
    common = [
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={VIDEO_W}x{VIDEO_H}:d={BROLL_SLUG_SECONDS}:r={FPS}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
        "-t",
        str(BROLL_SLUG_SECONDS),
    ]
    tail = [
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "2",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        dest,
    ]

    font = _find_font()
    label = (label or "B-ROLL").strip()
    if font:
        textfile = os.path.join(workdir, "broll_label.txt")
        with open(textfile, "w", encoding="utf-8") as fh:
            fh.write(f"[B-ROLL] {label}")
        drawtext = (
            f"drawtext=fontfile={font}:textfile={textfile}:"
            "fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2,format=yuv420p"
        )
        proc = _ffmpeg([*common, "-vf", drawtext, *tail])
        if proc.returncode == 0 and os.path.exists(dest):
            return

    proc = _ffmpeg([*common, "-vf", "format=yuv420p", *tail])
    if proc.returncode != 0 or not os.path.exists(dest):
        raise AssembleError(f"falha ao gerar slug de B-roll: {proc.stderr.strip()}")


def _concat(segment_files: list[str], output_path: str, workdir: str) -> None:
    listfile = os.path.join(workdir, "concat.txt")
    with open(listfile, "w", encoding="utf-8") as fh:
        for seg in segment_files:
            fh.write(f"file '{os.path.abspath(seg)}'\n")
    proc = _ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", output_path]
    )
    if proc.returncode != 0 or not os.path.exists(output_path):
        raise AssembleError(f"falha ao concatenar: {proc.stderr.strip()}")


def assemble(cut_list: dict, clip_map: dict[str, str], output_path: str) -> list[_Segment]:
    """Monta o stringout a partir da cut-list.

    `clip_map` mapeia clip_id -> caminho do arquivo de vídeo.
    Retorna a lista de segmentos (na ordem final), útil para os testes.
    """
    _require_ffmpeg()
    beats = cut_list.get("roughcut")
    if not isinstance(beats, list) or not beats:
        raise AssembleError("cut-list vazia ou sem a chave 'roughcut'")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    segments: list[_Segment] = []
    segment_files: list[str] = []
    with tempfile.TemporaryDirectory(prefix="roughcut_assemble_") as workdir:
        idx = 0
        for beat in beats:
            beat_name = beat.get("beat", f"beat_{idx}")
            clips = beat.get("clips") or []
            if clips:
                for clip in clips:
                    clip_id = clip["clip_id"]
                    if clip_id not in clip_map:
                        raise AssembleError(
                            f"clip_id {clip_id!r} não está no clip_map"
                        )
                    start = parse_timecode(clip["in"])
                    end = parse_timecode(clip["out"])
                    duration = end - start
                    dest = os.path.join(workdir, f"seg_{idx:03d}.mp4")
                    _cut_clip(clip_map[clip_id], start, duration, dest)
                    segment_files.append(dest)
                    segments.append(_Segment(beat_name, "clip", duration))
                    idx += 1
            else:
                dest = os.path.join(workdir, f"seg_{idx:03d}.mp4")
                _make_broll_slug(beat.get("broll_suggestion", ""), dest, workdir)
                segment_files.append(dest)
                segments.append(_Segment(beat_name, "broll", float(BROLL_SLUG_SECONDS)))
                idx += 1

        if not segment_files:
            raise AssembleError("nenhum segmento gerado a partir da cut-list")
        _concat(segment_files, output_path, workdir)

    return segments


def load_cut_list(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_clip_map(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
