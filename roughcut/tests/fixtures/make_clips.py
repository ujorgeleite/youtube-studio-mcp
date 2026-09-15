"""Gera clipes de amostra para os testes de assemble.

Cada clipe é uma cor sólida (para os testes checarem a ORDEM dos segmentos pela
cor dominante) com uma trilha de áudio senoidal. Os clipes NÃO são commitados
(ver .gitignore); são gerados num diretório temporário na hora do teste.
"""

from __future__ import annotations

import os
import subprocess

CLIPS = {
    "C01": {"color": "red", "rgb": (255, 0, 0)},
    "C02": {"color": "green", "rgb": (0, 128, 0)},
    "C03": {"color": "blue", "rgb": (0, 0, 255)},
}
CLIP_SECONDS = 5


def make_clips(dest_dir: str) -> dict[str, str]:
    """Cria os 3 clipes em `dest_dir`. Retorna o clip_map (clip_id -> caminho)."""
    os.makedirs(dest_dir, exist_ok=True)
    clip_map: dict[str, str] = {}
    for clip_id, meta in CLIPS.items():
        path = os.path.join(dest_dir, f"{clip_id}.mp4")
        freq = 220 + 110 * list(CLIPS).index(clip_id)
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i",
                f"color=c={meta['color']}:s=640x360:d={CLIP_SECONDS}:r=30",
                "-f", "lavfi", "-i",
                f"sine=frequency={freq}:duration={CLIP_SECONDS}:sample_rate=44100",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", path,
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not os.path.exists(path):
            raise RuntimeError(f"falha ao gerar {clip_id}: {proc.stderr.strip()}")
        clip_map[clip_id] = path
    return clip_map


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    print(make_clips(target))
