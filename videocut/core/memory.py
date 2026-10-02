"""Memória do Mac: quanto está livre, quanto foi para o swap e quem está ocupando.

Só leitura. Os números seguem o Monitor de Atividade: disponível = páginas
livres + inativas + especulativas + purgáveis; uso por app = footprint do `top`,
somando os processos auxiliares de cada aplicativo.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .config import models, vision_options

Runner = Callable[[list[str]], str]
GB = 1024 ** 3
SWAP_WARNING_GB = 4.0
PRESSURE_LABELS = {1: "normal", 2: "alta", 4: "crítica"}
DEFAULT_MODEL_MEMORY_GB = 8.0


def run_command(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


@dataclass(frozen=True)
class AppMemory:
    name: str
    bytes: int
    processes: int

    @property
    def gb(self) -> float:
        return self.bytes / GB


@dataclass
class MemoryStatus:
    total: int = 0
    available: int = 0
    swap_used: int = 0
    pressure: int | None = None
    apps: list[AppMemory] = field(default_factory=list)

    @property
    def available_gb(self) -> float:
        return self.available / GB

    @property
    def total_gb(self) -> float:
        return self.total / GB

    @property
    def used_fraction(self) -> float:
        return 1 - self.available / self.total if self.total else 0.0

    @property
    def swap_gb(self) -> float:
        return self.swap_used / GB

    @property
    def pressure_label(self) -> str:
        return PRESSURE_LABELS.get(self.pressure or 0, "desconhecida")

    def level(self, required_gb: float) -> str:
        """ok, apertado ou critico para rodar um modelo que precisa de `required_gb`."""
        if self.pressure == 4 or self.available_gb < required_gb * 0.6:
            return "critico"
        if self.pressure == 2 or self.available_gb < required_gb or self.swap_gb >= SWAP_WARNING_GB:
            return "apertado"
        return "ok"


def required_gb(model_key: str | None) -> float:
    """Sem escolha no projeto, vale o modelo padrão de `config/modelos.yaml`."""
    key = model_key or models().get("vision", {}).get("default", "")
    option = vision_options().get(key, {})
    return float(option.get("memory_gb", DEFAULT_MODEL_MEMORY_GB))


def parse_vm_stat(output: str) -> int:
    page = re.search(r"page size of (\d+) bytes", output)
    size = int(page.group(1)) if page else 16384
    pages = 0
    for key in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"):
        match = re.search(rf"{key}:\s+(\d+)", output)
        pages += int(match.group(1)) if match else 0
    return pages * size


def parse_swap(output: str) -> int:
    match = re.search(r"used = ([\d.]+)([MG])", output)
    if not match:
        return 0
    value = float(match.group(1))
    return int(value * (GB if match.group(2) == "G" else 1024 ** 2))


def parse_size(text: str) -> int:
    match = re.match(r"([\d.]+)([BKMG])", text.strip())
    if not match:
        return 0
    return int(float(match.group(1)) * {"B": 1, "K": 1024, "M": 1024 ** 2, "G": GB}[match.group(2)])


def app_name(path: str) -> str:
    """Processos auxiliares contam para o app de fora: `/Applications/Brave Browser.app/...` → Brave Browser."""
    match = re.search(r"/([^/]+)\.app/", path + "/")
    if match:
        return match.group(1)
    base = path.rsplit("/", 1)[-1]
    if base.startswith("com.apple.Virtualization"):
        return "Máquina virtual (Virtualization)"
    return base or "?"


def top_apps(runner: Runner = run_command, limit: int = 8) -> list[AppMemory]:
    footprints: dict[int, int] = {}
    for line in runner(["top", "-l", "1", "-o", "mem", "-n", "400", "-stats", "pid,mem"]).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            footprints[int(parts[0])] = parse_size(parts[1].rstrip("+-"))
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for line in runner(["ps", "-axo", "pid=,comm="]).splitlines():
        pid_text, _, path = line.strip().partition(" ")
        if not pid_text.isdigit() or int(pid_text) not in footprints:
            continue
        name = app_name(path.strip())
        totals[name] += footprints[int(pid_text)]
        counts[name] += 1
    apps = [AppMemory(name, size, counts[name]) for name, size in totals.items()]
    return sorted(apps, key=lambda app: -app.bytes)[:limit]


def memory_status(runner: Runner = run_command, with_apps: bool = True) -> MemoryStatus:
    total = runner(["sysctl", "-n", "hw.memsize"]).strip()
    pressure = runner(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
    return MemoryStatus(
        total=int(total) if total.isdigit() else 0,
        available=parse_vm_stat(runner(["vm_stat"])),
        swap_used=parse_swap(runner(["sysctl", "-n", "vm.swapusage"])),
        pressure=int(pressure) if pressure.isdigit() else None,
        apps=top_apps(runner) if with_apps else [],
    )


def gb_text(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " GB"


BROWSERS = ("browser", "safari", "chrome", "firefox", "arc", "edge", "opera")


def freeing_hint(app: AppMemory) -> str:
    lowered = app.name.lower()
    if any(word in lowered for word in BROWSERS):
        return "feche abas e janelas que não estiver usando"
    if "virtualization" in lowered or "docker" in lowered:
        return "encerre a máquina virtual ou o Docker se não estiver usando"
    return "feche o app (⌘Q) durante a análise"


def freeing_steps(status: MemoryStatus, required: float) -> list[str]:
    """Passo a passo montado a partir do que está aberto agora."""
    steps = []
    missing = max(0.0, required - status.available_gb)
    if missing:
        steps.append(f"Libere pelo menos {gb_text(missing)}: o modelo escolhido precisa de ~{required:g} GB livres.")
    heavy = [app for app in status.apps if app.gb >= 0.5 and not app.name.lower().startswith(("videocut", "python", "kernel_task", "windowserver"))]
    for app in heavy[:4]:
        processes = f" em {app.processes} processos" if app.processes > 1 else ""
        steps.append(f"{app.name} usa {gb_text(app.gb)}{processes}: {freeing_hint(app)}.")
    if status.swap_gb >= SWAP_WARNING_GB:
        steps.append(f"Há {gb_text(status.swap_gb)} em swap (memória jogada no disco). Depois de fechar os apps, se continuar "
                     f"acima de {SWAP_WARNING_GB:g} GB, reinicie o Mac antes de uma análise longa.")
    steps.append("Se não der para fechar nada, escolha o modelo Qwen3-VL 4B, que precisa de menos memória.")
    steps.append("Confira em Monitor de Atividade → Memória; a “Pressão de memória” deve ficar verde.")
    return steps


def open_activity_monitor() -> None:
    subprocess.run(["open", "-a", "Activity Monitor"], check=False)
