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
from steps.order import (  # noqa: E402
    build_prompt,
    load_format,
    load_prompt_template,
    order,
    parse_cut_list,
)
from steps.run_record import RunRecord  # noqa: E402
from steps.transcribe import list_clips, transcribe_folder  # noqa: E402

FORMATS_DIR = os.path.join(HERE, "formats")
PROMPT_PATH = os.path.join(HERE, "prompts", "ordenacao.md")
FIXTURE_CUT_LIST = os.path.join(HERE, "tests", "fixtures", "cut_list.json")
RUNS_DIR = os.path.join(HERE, "runs")


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


def _clip_progress(record: RunRecord):
    return lambda clip_id, index, total, path: record.event(
        "transcribe", "clip", clip_id=clip_id, index=index, total=total, filename=os.path.basename(path)
    )


def _save_cut_list_artifacts(record: RunRecord, cut_list: dict) -> None:
    record.artifact("cut_list", cut_list, filename="cut-list.json")
    if cut_list.get("critica"):
        record.artifact("critica", cut_list["critica"], filename="critica.json")


def list_formats() -> list[str]:
    if not os.path.isdir(FORMATS_DIR):
        return []
    names = (
        os.path.splitext(f)[0]
        for f in os.listdir(FORMATS_DIR)
        if f.endswith((".yaml", ".yml"))
    )
    return sorted(names)


def run_dry(
    *,
    output: str,
    cut_list: str | None = None,
    input: str | None = None,
    record: RunRecord | None = None,
) -> RunRecord:
    """Assemble-only: reprocessa a partir de um cut-list pronto (ou o de fixture).

    `record` já criado (ex.: pela UI, que precisa do diretório antes do run) é
    reutilizado; caso contrário um novo é aberto.
    """
    source = cut_list or FIXTURE_CUT_LIST
    if record is None:
        record = RunRecord.create(
            RUNS_DIR, {"mode": "dry", "cut_list": source, "input": input, "output": output}
        )
    try:
        parsed = load_cut_list(source)
        _save_cut_list_artifacts(record, parsed)

        if input:
            clip_map = list_clips(input)
        else:
            from tests.fixtures.make_clips import make_clips

            demo_dir = tempfile.mkdtemp(prefix="roughcut_demo_clips_")
            clip_map = make_clips(demo_dir)
            print(f"[dry-run] usando clipes de demonstração em {demo_dir}")
        record.event("assemble", "clips_resolved", count=len(clip_map), clip_ids=list(clip_map))

        with record.step("assemble", output=output):
            assemble(
                parsed,
                clip_map,
                output,
                on_progress=lambda event, payload: record.event("assemble", event, **payload),
            )
        record.note_output("stringout", output)
    except Exception as exc:
        record.finalize("error", error=str(exc))
        print(f"  run: {record.dir}")
        raise
    record.finalize("ok")
    _print_critica(parsed)
    print(f"  run: {record.dir}")
    return record


def build_order_prompt(transcripts: str, format: str = "qualidade-de-vida") -> str:
    template = load_prompt_template(PROMPT_PATH)
    format_yaml = load_format(_format_path(format))
    return build_prompt(template, format_yaml, transcripts)


def transcribe_and_prompt(
    *,
    input: str,
    format: str = "qualidade-de-vida",
    model_size: str = "base",
    record: RunRecord | None = None,
) -> tuple[str, dict[str, str]]:
    """Fase manual A: transcreve localmente e monta o prompt para uma IA externa.

    Não chama LLM nenhum. Devolve (prompt, clip_map) — o clip_map segue para o
    assemble depois que o humano trouxer a resposta (assemble_from_raw).
    """
    if record is None:
        record = RunRecord.create(
            RUNS_DIR,
            {"mode": "manual", "format": format, "model_size": model_size, "input": input},
        )
    with record.step("transcribe", input=input, model_size=model_size):
        transcripts, clip_map = transcribe_folder(
            input, model_size=model_size, on_clip=_clip_progress(record)
        )
    record.artifact("transcripts", transcripts, filename="transcripts.txt")
    record.event("transcribe", "clips_transcribed", count=len(clip_map), clip_ids=list(clip_map))

    prompt = build_order_prompt(transcripts, format)
    record.artifact("prompt", prompt, filename="prompt.md")
    record.event("order", "prompt_ready", chars=len(prompt), source="manual")
    return prompt, clip_map


def record_response(record: RunRecord, raw: str) -> dict:
    """Fase manual B1: guarda a resposta crua da IA e faz parse da cut-list.

    Não monta nada — o usuário revisa/reordena a prévia antes de aprovar.
    """
    record.artifact("llm_response", raw, filename="llm_response.txt")
    record.event("order", "response_received", chars=len(raw), source="manual")
    cut_list = parse_cut_list(raw)
    _save_cut_list_artifacts(record, cut_list)
    return cut_list


def assemble_approved(
    *,
    cut_list: dict,
    clip_map: dict[str, str],
    output: str,
    record: RunRecord,
) -> dict:
    """Fase manual B2: monta o stringout a partir da cut-list aprovada (talvez editada)."""
    _save_cut_list_artifacts(record, cut_list)
    try:
        with record.step("assemble", output=output):
            assemble(
                cut_list,
                clip_map,
                output,
                on_progress=lambda event, payload: record.event("assemble", event, **payload),
            )
        record.note_output("stringout", output)
    except Exception as exc:
        record.finalize("error", error=str(exc))
        print(f"  run: {record.dir}")
        raise
    record.finalize("ok")
    _print_critica(cut_list)
    print(f"  run: {record.dir}")
    return cut_list


def assemble_from_raw(
    *,
    raw: str,
    clip_map: dict[str, str],
    output: str,
    record: RunRecord,
) -> dict:
    """Fase manual B em um passo (parse + montagem), sem revisão. Usada pela CLI/testes."""
    try:
        cut_list = record_response(record, raw)
    except Exception as exc:
        record.finalize("error", error=str(exc))
        print(f"  run: {record.dir}")
        raise
    return assemble_approved(cut_list=cut_list, clip_map=clip_map, output=output, record=record)


def run_full(
    *,
    input: str,
    format: str = "qualidade-de-vida",
    output: str = "stringout.mp4",
    model_size: str = "base",
    record: RunRecord | None = None,
) -> RunRecord:
    """Pipeline completo (transcribe -> order -> assemble), instrumentado.

    `record` já criado é reutilizado (ver run_dry).
    """
    format_path = _format_path(format)
    if record is None:
        record = RunRecord.create(
            RUNS_DIR,
            {
                "mode": "full",
                "format": format,
                "model_size": model_size,
                "input": input,
                "output": output,
            },
        )
    try:
        print(f"[1/3] transcrevendo clipes de {input} ...")
        with record.step("transcribe", input=input, model_size=model_size):
            transcripts, clip_map = transcribe_folder(
                input, model_size=model_size, on_clip=_clip_progress(record)
            )
        record.artifact("transcripts", transcripts, filename="transcripts.txt")
        record.event("transcribe", "clips_transcribed", count=len(clip_map), clip_ids=list(clip_map))

        print("[2/3] ordenando (LLM) ...")
        with record.step("order", format=format_path):
            cut_list = order(
                transcripts,
                format_path,
                PROMPT_PATH,
                on_prompt=lambda prompt: record.artifact("prompt", prompt, filename="prompt.md"),
                on_raw=lambda raw: record.artifact("llm_response", raw, filename="llm_response.txt"),
            )
        _save_cut_list_artifacts(record, cut_list)

        cut_list_path = os.path.splitext(output)[0] + ".cut-list.json"
        with open(cut_list_path, "w", encoding="utf-8") as fh:
            json.dump(cut_list, fh, ensure_ascii=False, indent=2)
        print(f"      cut-list salva em {cut_list_path}")

        print("[3/3] montando o stringout (ffmpeg) ...")
        with record.step("assemble", output=output):
            assemble(
                cut_list,
                clip_map,
                output,
                on_progress=lambda event, payload: record.event("assemble", event, **payload),
            )
        record.note_output("stringout", output)
    except Exception as exc:
        record.finalize("error", error=str(exc))
        print(f"  run: {record.dir}")
        raise
    record.finalize("ok")
    _print_critica(cut_list)
    print(f"  run: {record.dir}")
    return record


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
        run_dry(output=args.output, cut_list=args.cut_list, input=args.input)
    else:
        if not args.input:
            raise SystemExit("--input é obrigatório (ou use --dry-run)")
        run_full(
            input=args.input,
            format=args.format,
            output=args.output,
            model_size=args.model_size,
        )
    print(f"\n✓ stringout: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
