"""Leitura dos ajustes de energia para rodar de madrugada. Nada aqui altera o sistema."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable

Runner = Callable[[list[str]], str]
BATTERY_SETTINGS = "x-apple.systempreferences:com.apple.Battery-Settings.extension"
UPDATE_SETTINGS = "x-apple.systempreferences:com.apple.Software-Update-Settings.extension"


def run_command(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


@dataclass(frozen=True)
class CheckItem:
    key: str
    label: str
    ok: bool | None
    detail: str
    settings: str | None = None

    @property
    def status(self) -> str:
        return "ok" if self.ok else "pendente" if self.ok is False else "lembrete"


def on_ac_power(runner: Runner = run_command) -> bool | None:
    output = runner(["pmset", "-g", "batt"])
    if "AC Power" in output:
        return True
    if "Battery Power" in output:
        return False
    return None


def battery_percent(runner: Runner = run_command) -> int | None:
    match = re.search(r"(\d+)%", runner(["pmset", "-g", "batt"]))
    return int(match.group(1)) if match else None


def low_power_mode(runner: Runner = run_command) -> bool | None:
    match = re.search(r"^\s*lowpowermode\s+(\d)", runner(["pmset", "-g"]), re.MULTILINE)
    return match.group(1) == "1" if match else None


def auto_install_macos_updates(runner: Runner = run_command) -> bool | None:
    output = runner(["defaults", "read", "/Library/Preferences/com.apple.SoftwareUpdate", "AutomaticallyInstallMacOSUpdates"]).strip()
    return {"1": True, "0": False}.get(output)


def caffeinate_active(pid: int, runner: Runner = run_command) -> bool:
    """O `caffeinate` do VideoCut aparece nas asserções com `-w <pid do app>`."""
    processes = runner(["pgrep", "-fl", f"caffeinate .*-w {pid}"])
    return bool(processes.strip())


def power_checklist(pid: int, runner: Runner = run_command) -> list[CheckItem]:
    ac = on_ac_power(runner)
    percent = battery_percent(runner)
    low_power = low_power_mode(runner)
    updates = auto_install_macos_updates(runner)
    awake = caffeinate_active(pid, runner)
    return [
        CheckItem("tomada", "Ligado na tomada", ac,
                  "Na tomada." if ac else f"Na bateria ({percent}%). Ligue o carregador para rodar por horas." if ac is False
                  else "Não foi possível ler a fonte de energia."),
        CheckItem("baixo_consumo", "Modo de Baixo Consumo desligado", None if low_power is None else not low_power,
                  "Desligado." if low_power is False else "Ligado: deixa a análise bem mais lenta. Ajuste para “Nunca”." if low_power
                  else "Não foi possível ler.", BATTERY_SETTINGS),
        CheckItem("atualizacoes", "Sem instalação automática do macOS", None if updates is None else not updates,
                  "Instalação automática desligada." if updates is False
                  else "Ligada: o Mac pode reiniciar de madrugada para atualizar." if updates
                  else "Não foi possível ler; confira em Atualização de Software.", UPDATE_SETTINGS),
        CheckItem("tampa", "Tampa aberta", None,
                  "Deixe a tampa aberta: sem monitor externo, o Mac dorme ao fechar. A tela pode apagar sozinha."),
        CheckItem("acordado", "Mac mantido acordado pelo VideoCut", True if awake else None,
                  "Ativo agora: o sistema e o disco não dormem; a tela pode apagar." if awake
                  else "Liga sozinho quando a análise ou o render começarem."),
    ]


def open_settings(url: str) -> None:
    subprocess.run(["open", url], check=False)
