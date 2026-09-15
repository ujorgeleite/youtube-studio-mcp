"""Entrypoint do roughcut: orquestra os 3 passos.

    passo 1 (transcribe)  ->  passo 2 (order)  ->  passo 3 (assemble)

Uso:
    python run.py --input ./clipes_brutos --format qualidade-de-vida --output ./stringout.mp4

Modo --dry-run: pula Whisper e LLM e roda só o assemble a partir de um cut-list já
salvo (útil para reprocessar sem recomputar). Sem --cut-list e sem --input, roda
uma demonstração autocontida com a cut-list e os clipes de fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from steps.assemble import assemble, load_cut_list  # noqa: E402
from steps.order import order  # noqa: E402
from steps.transcribe import list_clips, transcribe_folder  # noqa: E402

FORMATS_DIR = os.path.join(HERE, "formats")
PROMPT_PATH = os.path.join(HERE, "prompts", "ordenacao.md")
FIXTURE_CUT_LIST = os.path.join(HERE, "tests", "fixtures", "cut_list.json")


def _format_path(name: str) -> str:
    if os.path.isfile(name):
        return name
    candidate = os.path.join(FORMATS_DIR, f"{name}.yaml")
    if not os.path.isfile(candidate):
        raise SystemExit(f"formato não encontrado: {name} (procurei em {candidate})")
    return candidate


def _print_critica(cut_list: dict) -> None:
    critica = cut_list.get("critica")
    if not critica:
        return
    print("\n=== crítica da ordenação ===")
    for key in ("gaps", "redundancia", "ordem", "orfaos", "hook_candidates"):
        val = critica.get(key)
        if val:
            if isinstance(val, list):
                print(f"{key}:")
                for item in val:
                    print(f"  - {item}")
            else:
                print(f"{key}: {val}")
    if "duracao_estimada_s" in critica:
        print(f"duracao_estimada_s: {critica['duracao_estimada_s']}")


def _run_dry(args) -> str:
    cut_list = load_cut_list(args.cut_list) if args.cut_list else load_cut_list(
        FIXTURE_CUT_LIST
    )
    if args.input:
        clip_map = list_clips(args.input)
    else:
        from tests.fixtures.make_clips import make_clips

        demo_dir = tempfile.mkdtemp(prefix="roughcut_demo_clips_")
        clip_map = make_clips(demo_dir)
        print(f"[dry-run] usando clipes de demonstração em {demo_dir}")

    assemble(cut_list, clip_map, args.output)
    _print_critica(cut_list)
    return args.output


def _run_full(args) -> str:
    format_path = _format_path(args.format)
    print(f"[1/3] transcrevendo clipes de {args.input} ...")
    transcripts, clip_map = transcribe_folder(args.input, model_size=args.model_size)

    print("[2/3] ordenando (LLM) ...")
    cut_list = order(transcripts, format_path, PROMPT_PATH)

    cut_list_path = os.path.splitext(args.output)[0] + ".cut-list.json"
    with open(cut_list_path, "w", encoding="utf-8") as fh:
        json.dump(cut_list, fh, ensure_ascii=False, indent=2)
    print(f"      cut-list salva em {cut_list_path}")

    print("[3/3] montando o stringout (ffmpeg) ...")
    assemble(cut_list, clip_map, args.output)
    _print_critica(cut_list)
    return args.output


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run.py", description="roughcut — pipeline de pré-montagem de vídeo"
    )
    p.add_argument("--input", help="pasta com os clipes brutos")
    p.add_argument("--format", default="qualidade-de-vida", help="nome do formato")
    p.add_argument("--output", default="stringout.mp4", help="MP4 de saída")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="pula Whisper e LLM; roda só o assemble a partir de um cut-list",
    )
    p.add_argument(
        "--cut-list",
        help="cut-list JSON pronto (usado no --dry-run)",
    )
    p.add_argument(
        "--model-size",
        default="base",
        help="tamanho do modelo Whisper (tiny/base/small/...)",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        out = _run_dry(args)
    else:
        if not args.input:
            raise SystemExit("--input é obrigatório (ou use --dry-run)")
        out = _run_full(args)
    print(f"\n✓ stringout: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
