"""Linha de comando: diagnóstico, análise sem interface, prova contra edição real e benchmark."""

from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Thread
from time import sleep

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis.pipeline import Analysis, AnalysisMonitor, load_inventory  # noqa: E402
from analysis.speech import transcribe_take  # noqa: E402
from core.config import min_take_s, model_cached, models, vision_options  # noqa: E402
from core.offline import enable_offline  # noqa: E402
from core.project import Project  # noqa: E402
from core.safety import SourceProtectionError, write_text  # noqa: E402
from core.serial import write_json  # noqa: E402
from media.audio import extract_speech_audio  # noqa: E402
from media.catalog import catalog_folder  # noqa: E402
from media.probe import probe  # noqa: E402

def doctor(_: argparse.Namespace) -> int:
    ok = True
    for binary in ("ffmpeg", "ffprobe"):
        found = shutil.which(binary)
        ok &= bool(found)
        print(f"{'✓' if found else '✗'} {binary}: {found or 'não encontrado (brew install ffmpeg)'}")
    for module in ("nicegui", "mlx_whisper", "mlx_vlm", "yaml"):
        try:
            importlib.import_module(module)
            print(f"✓ python: {module}")
        except ImportError:
            ok = False
            print(f"✗ python: {module} ausente (make install)")
    memory = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()
    if memory.isdigit():
        gigabytes = int(memory) / 1024 ** 3
        print(f"✓ memória: {gigabytes:.0f} GB" + ("  (8B recomendado)" if gigabytes >= 16 else "  (use o 4B)"))
    repos = {"whisper": models().get("whisper", "")} | {key: value["repo"] for key, value in vision_options().items()}
    for key, repo in repos.items():
        print(f"{'✓' if model_cached(repo) else '·'} modelo {key}: {repo}" + ("" if model_cached(repo) else " (baixa na primeira análise)"))
    print("Pronto." if ok else "Corrija os itens com ✗.")
    return 0 if ok else 1


def download_models(args: argparse.Namespace) -> int:
    from analysis.models import ModelDownloadError, ensure_model

    options = vision_options()
    keys = args.models.split(",") if args.models else [models().get("vision", {}).get("default")]
    targets = [("Whisper", models().get("whisper"))] + [(key, options[key]["repo"]) for key in keys]
    for label, repo in targets:
        try:
            ensure_model(repo, label, lambda fraction, message: print(f"  {message}", end="\r", flush=True))
        except ModelDownloadError as error:
            print(f"\n✗ {error}")
            return 1
        print(f"\n✓ {label}: {repo}")
    return 0


def _open_project(folder: str, output: str | None, min_take: float = 0.0) -> Project:
    project = Project.open(folder, output)
    takes, errors = catalog_folder(project.folder, project.layout.thumbnails, project.takes)
    for name, error in errors.items():
        print(f"ignorado {name}: {error}")
    for take in project.merge_takes(takes, min_take):
        print(f"desmarcado por ser curto ({take.duration_s:.1f} s): {take.id} · {take.name}")
    return project


def analyze(args: argparse.Namespace) -> int:
    project = _open_project(args.folder, args.output, args.min_take_s)
    project.intention = args.intention or project.intention
    project.model = args.model or project.model
    project.target_minutes = args.minutes or project.target_minutes
    project.save()
    monitor = AnalysisMonitor()
    worker = Thread(target=lambda: _run(Analysis(project, monitor)), daemon=True)
    worker.start()
    printed = 0
    while worker.is_alive():
        sleep(1)
        for line in monitor.log[printed:]:
            print(f"  {line}")
        printed = len(monitor.log)
        print(f"[{monitor.elapsed_s:6.0f}s] {monitor.message}", end="\r", flush=True)
    print()
    if monitor.error:
        print(f"falhou: {monitor.error}")
        return 1
    for proposal in project.report.proposals:
        print(f"{proposal.id} · {proposal.title}" + (" (recomendada)" if proposal.recommended else ""))
    print(f"Projeto salvo em {project.layout.project_file}")
    return 0


def _run(analysis: Analysis) -> None:
    try:
        analysis.run()
    except Exception:  # noqa: BLE001 - o erro fica em monitor.error e é impresso pelo laço principal
        pass


def compare_edit(args: argparse.Namespace) -> int:
    from proof.compare import compare, comparison_report, write_comparison

    project = Project.open(args.folder, args.output)
    inventory = load_inventory(project)
    if project.report is None or inventory is None:
        print("Analise o material antes (make analyze).")
        return 1
    proposal = project.report.proposal(args.proposal) if args.proposal else next(p for p in project.report.proposals if p.recommended)
    video = next((video for video in proposal.videos if video.id == args.video), proposal.videos[0])
    edit = Path(args.edit).expanduser().resolve()
    audio = extract_speech_audio(edit, project.layout.audio / f"edicao__{edit.stem}.wav")
    transcript = transcribe_take("EDIT", edit, audio, project.layout.cache)
    result = compare(transcript, probe(edit).duration_s, video, project.review.get(video.id), inventory)
    target = write_comparison(comparison_report(result, inventory, edit.name, video), project.layout.analysis / f"comparacao__{video.id}.md")
    print(f"recall {result.recall:.0%} · precisão {result.precision:.0%} · ordem {result.order_agreement:.0%}")
    print(f"Relatório: {target}")
    return 0


def benchmark_models(args: argparse.Namespace) -> int:
    from proof.benchmark import benchmark, benchmark_report

    project = Project.open(args.folder, args.output)
    inventory = load_inventory(project)
    takes = [take for take in project.takes if not args.takes or take.id in args.takes.split(",")]
    transcripts = inventory.transcripts if inventory else {}
    keys = args.models.split(",") if args.models else None
    runs = benchmark(takes, transcripts, project.layout.work / "benchmark", keys)
    target = write_text(project.layout.analysis / "benchmark.md", benchmark_report(runs, takes))
    write_json(project.layout.analysis / "benchmark.json", [{"model": run.key, "seconds": run.material_s, "peak_gb": run.peak_gb,
                                                               "calls": run.calls, "invalid": run.invalid, "error": run.error} for run in runs])
    print(f"Relatório: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="videocut")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="verifica ffmpeg, dependências, memória e modelos").set_defaults(handler=doctor)
    fetch = commands.add_parser("models", help="baixa os modelos antes do primeiro uso, com progresso")
    fetch.add_argument("--models", help="ex.: qwen3-vl-4b,qwen3-vl-8b (padrão: o modelo configurado)")
    fetch.set_defaults(handler=download_models)
    for name, handler, help_text in (("analyze", analyze, "analisa uma pasta sem abrir a interface"),
                                     ("compare", compare_edit, "compara a proposta com uma edição já feita"),
                                     ("benchmark", benchmark_models, "mede os modelos visuais no seu material")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("folder")
        command.add_argument("--output")
        command.set_defaults(handler=handler)
        if name == "analyze":
            command.add_argument("--intention", default="")
            command.add_argument("--model", choices=list(vision_options()))
            command.add_argument("--minutes", type=float)
            command.add_argument("--min-take-s", type=float, default=min_take_s(),
                                 help="takes novos mais curtos ficam fora da análise (padrão: config/modelos.yaml)")
        if name == "compare":
            command.add_argument("edit", help="MP4 da sua edição final")
            command.add_argument("--proposal")
            command.add_argument("--video")
        if name == "benchmark":
            command.add_argument("--takes", help="ex.: T01,T03")
            command.add_argument("--models", help="ex.: qwen3-vl-4b,qwen3-vl-8b")
    args = parser.parse_args(argv)
    if args.command != "models":
        enable_offline()
    try:
        return args.handler(args)
    except SourceProtectionError as error:
        print(f"bloqueado: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
