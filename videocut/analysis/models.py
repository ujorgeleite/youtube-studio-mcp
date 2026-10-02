"""Download dos modelos com progresso real e vigia contra travamentos.

O cliente paralelo (hf_xet) pode ficar parado para sempre quando o CDN fecha as
conexões. Por isso o download roda em subprocesso, sem xet (HTTPS com timeout
de leitura e retomada), e é reiniciado se passar tempo demais sem receber bytes.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from core.config import HF_CACHE
from core.offline import online_environment

Progress = Callable[[float, str], None]
STALL_TIMEOUT_S = 90.0
ATTEMPTS = 5
POLL_S = 1.0
ORPHAN_AGE_S = 60.0


class ModelDownloadError(RuntimeError):
    pass


def repo_dir(repo: str) -> Path:
    return HF_CACHE / f"models--{repo.replace('/', '--')}"


def downloaded_bytes(repo: str) -> int:
    blobs = repo_dir(repo) / "blobs"
    return sum(path.stat().st_size for path in blobs.iterdir() if path.is_file()) if blobs.is_dir() else 0


def incomplete_files(repo: str) -> list[Path]:
    blobs = repo_dir(repo) / "blobs"
    return sorted(blobs.glob("*.incomplete")) if blobs.is_dir() else []


def is_complete(repo: str) -> bool:
    """Sem parciais e com o snapshot resolvível sem rede."""
    if incomplete_files(repo) or not repo_dir(repo).is_dir():
        return False
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo, local_files_only=True)
    except Exception:  # noqa: BLE001 - qualquer falha local significa "falta baixar"
        return False
    return True


def expected_bytes(repo: str) -> int:
    """Consulta direta à API: funciona mesmo com o processo principal em modo offline."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=15) as response:
            info = json.load(response)
    except Exception:  # noqa: BLE001 - sem tamanho total, o progresso mostra só o volume baixado
        return 0
    return sum(sibling.get("size") or 0 for sibling in info.get("siblings", []))


def discard_orphans(repo: str, now: float | None = None) -> list[Path]:
    """Parciais parados vêm de um download interrompido e podem estar fora de ordem."""
    moment = now or time.time()
    removed = []
    for path in incomplete_files(repo):
        if moment - path.stat().st_mtime >= ORPHAN_AGE_S:
            path.unlink()
            removed.append(path)
    return removed


def download_command(repo: str) -> list[str]:
    return [sys.executable, "-c", f"from huggingface_hub import snapshot_download; snapshot_download({repo!r})"]


def _gigabytes(value: int) -> str:
    return f"{value / 1e9:.1f}".replace(".", ",")


def ensure_model(
    repo: str,
    label: str,
    progress: Progress | None = None,
    *,
    command: Callable[[str], list[str]] = download_command,
    stall_timeout_s: float = STALL_TIMEOUT_S,
    attempts: int = ATTEMPTS,
) -> None:
    report = progress or (lambda fraction, message: None)
    if is_complete(repo):
        return
    total = expected_bytes(repo)
    environment = online_environment()
    for attempt in range(1, attempts + 1):
        discard_orphans(repo)
        log = tempfile.TemporaryFile(mode="w+")
        process = subprocess.Popen(command(repo), env=environment, stdout=subprocess.DEVNULL, stderr=log, text=True)
        last_size, last_change = downloaded_bytes(repo), time.monotonic()
        while process.poll() is None:
            time.sleep(POLL_S)
            size = downloaded_bytes(repo)
            if size != last_size:
                last_size, last_change = size, time.monotonic()
            fraction = min(size / total, 0.999) if total else 0.0
            detail = f"{_gigabytes(size)} de {_gigabytes(total)} GB" if total else f"{_gigabytes(size)} GB"
            retry = f" · tentativa {attempt}/{attempts}" if attempt > 1 else ""
            report(fraction, f"Baixando {label} · {fraction * 100:.0f}% ({detail}){retry}")
            if time.monotonic() - last_change > stall_timeout_s:
                process.kill()
                process.wait()
                break
        if process.returncode == 0 and is_complete(repo):
            report(1.0, f"{label} pronto")
            return
        log.seek(0)
        error = log.read().strip().splitlines()
        log.close()
        if process.returncode not in (0, -9):
            report(0.0, f"Falha ao baixar {label}: {error[-1][:160] if error else 'erro desconhecido'} · tentando de novo")
    raise ModelDownloadError(f"não foi possível baixar {label} ({repo}) após {attempts} tentativas; verifique a internet e tente de novo")
