from __future__ import annotations

import argparse
from pathlib import Path

from silence.analyze import list_videos

from .config import list_presets
from .pipeline import analyze_clip, default_output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roughcut smartcut", description="corte inteligente por fala/frase")
    command = parser.add_subparsers(dest="command", required=True)
    run = command.add_parser("run", help="analisa uma pasta de vídeos e gera planos revisáveis")
    run.add_argument("input", help="pasta raw")
    run.add_argument("--preset", choices=list_presets(), default="colab")
    run.add_argument("--output", help="pasta de saída; padrão é irmã da raw")
    run.add_argument("--refresh", action="store_true", help="ignora cache de VAD/transcrição")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_dir = Path(args.input).resolve()
    output = Path(args.output).resolve() if args.output else default_output_dir(input_dir)
    videos = list_videos(input_dir)
    if not videos:
        raise SystemExit("nenhum vídeo encontrado")
    for index, video in enumerate(videos, 1):
        print(f"[{index}/{len(videos)}] VAD + transcrição: {video.name}")
        plan, artifacts = analyze_clip(video, output, preset=args.preset, refresh=args.refresh)
        removed = sum(cut.end_s - cut.start_s for cut in plan.cuts)
        print(f"  {len(plan.cuts)} cortes · {removed:.1f}s removíveis · revisão: {artifacts['report']}")
    print(f"✓ saída: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
