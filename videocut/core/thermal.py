"""Temperatura do Mac e pausa para esfriar durante cargas longas.

O estado térmico do macOS (`NSProcessInfo.thermalState`) é lido sem dependências;
graus Celsius vêm do `macmon` (Apple Silicon, sem sudo) quando instalado.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .config import load_yaml

STATE_LABELS = {0: "normal", 1: "razoável", 2: "sério", 3: "crítico"}
READ_INTERVAL_S = 5.0


@dataclass(frozen=True)
class ThermalReading:
    state: int | None = None
    cpu_c: float | None = None
    gpu_c: float | None = None

    @property
    def hottest_c(self) -> float | None:
        values = [value for value in (self.cpu_c, self.gpu_c) if value is not None]
        return max(values) if values else None

    @property
    def label(self) -> str:
        parts = []
        if self.cpu_c is not None:
            parts.append(f"CPU {self.cpu_c:.0f} °C")
        if self.gpu_c is not None:
            parts.append(f"GPU {self.gpu_c:.0f} °C")
        if self.state is not None:
            parts.append(STATE_LABELS.get(self.state, str(self.state)))
        return " · ".join(parts) or "temperatura indisponível"


def thermal_state() -> int | None:
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", 'ObjC.import("Foundation"); $.NSProcessInfo.processInfo.thermalState'],
            capture_output=True, text=True, timeout=10,
        )
        return int(proc.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def macmon_available() -> bool:
    return shutil.which("macmon") is not None


def temperatures() -> tuple[float | None, float | None]:
    if not macmon_available():
        return None, None
    try:
        proc = subprocess.run(["macmon", "pipe", "-s", "1", "-i", "300"], capture_output=True, text=True, timeout=15)
        data = json.loads(proc.stdout.splitlines()[0]).get("temp", {})
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None, None
    return data.get("cpu_temp_avg"), data.get("gpu_temp_avg")


def read_thermal() -> ThermalReading:
    cpu, gpu = temperatures()
    return ThermalReading(thermal_state(), cpu, gpu)


@dataclass
class LongRunConfig:
    pause_state: int = 2
    resume_state: int = 1
    pause_temp_c: float = 95.0
    resume_temp_c: float = 80.0
    poll_s: float = 10.0
    max_wait_min: float = 45.0

    @classmethod
    def load(cls) -> "LongRunConfig":
        values = load_yaml("execucao.yaml").get("long_run", {})
        return cls(**{key: value for key, value in values.items() if key in cls.__dataclass_fields__})


@dataclass
class ThermalGovernor:
    """Com `enabled`, pausa acima do limite e só retoma abaixo do limite de volta (histerese).

    Desligado, continua lendo para mostrar a temperatura na tela, sem pausar.
    """

    enabled: bool = False
    config: LongRunConfig = field(default_factory=LongRunConfig.load)
    reader: Callable[[], ThermalReading] | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    cancel: threading.Event | None = None
    last: ThermalReading = field(default_factory=ThermalReading)
    last_read_at: float | None = None
    paused_since: float | None = None
    paused_total_s: float = 0.0
    pauses: int = 0
    warning: str | None = None

    def refresh(self, force: bool = False) -> ThermalReading:
        now = self.clock()
        if force or self.last_read_at is None or now - self.last_read_at >= READ_INTERVAL_S:
            self.last = (self.reader or read_thermal)()
            self.last_read_at = now
        return self.last

    def too_hot(self, reading: ThermalReading) -> bool:
        hot_state = reading.state is not None and reading.state >= self.config.pause_state
        hot_temp = reading.hottest_c is not None and reading.hottest_c >= self.config.pause_temp_c
        return hot_state or hot_temp

    def cool_enough(self, reading: ThermalReading) -> bool:
        state_ok = reading.state is None or reading.state <= self.config.resume_state
        temp_ok = reading.hottest_c is None or reading.hottest_c <= self.config.resume_temp_c
        return state_ok and temp_ok

    @property
    def paused_for_s(self) -> float:
        return self.clock() - self.paused_since if self.paused_since is not None else 0.0

    def wait_if_hot(self) -> None:
        reading = self.refresh()
        if not self.enabled or not self.too_hot(reading):
            return
        started = self.clock()
        self.paused_since = started
        self.pauses += 1
        try:
            while not (self.cancel and self.cancel.is_set()):
                if self.clock() - started >= self.config.max_wait_min * 60:
                    self.warning = (f"O Mac não esfriou em {self.config.max_wait_min:g} min "
                                    f"({self.last.label}); a execução continuou.")
                    break
                self.sleep(self.config.poll_s)
                if self.cool_enough(self.refresh(force=True)):
                    break
        finally:
            self.paused_total_s += self.clock() - started
            self.paused_since = None

    def summary(self) -> str:
        if not self.pauses:
            return ""
        minutes, seconds = divmod(int(self.paused_total_s), 60)
        return f"{self.pauses} pausa(s) para esfriar · {minutes} min {seconds:02d} s no total"
