"""Mantém o Mac acordado enquanto análise ou render rodam, sem mudar ajustes do sistema."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Callable

CAFFEINATE_FLAGS = ("-i", "-m", "-s")


class KeepAwake:
    """`caffeinate -i -m -s -w <pid>`: sem sono ocioso, sem sono do disco e, na tomada,
    sem sono do sistema. A tela pode apagar. `-w` encerra junto se o app morrer."""

    def __init__(self, spawn: Callable[..., subprocess.Popen] = subprocess.Popen, pid: int | None = None):
        self.spawn = spawn
        self.pid = pid or os.getpid()
        self.process: subprocess.Popen | None = None
        self.holders = 0

    @property
    def active(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def acquire(self) -> bool:
        """Contador de uso: análise e render podem segurar ao mesmo tempo."""
        self.holders += 1
        if self.active:
            return True
        if not shutil.which("caffeinate"):
            return False
        self.process = self.spawn(["caffeinate", *CAFFEINATE_FLAGS, "-w", str(self.pid)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def release(self) -> None:
        self.holders = max(0, self.holders - 1)
        if self.holders == 0 and self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None

    def __enter__(self) -> "KeepAwake":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


KEEP_AWAKE = KeepAwake()
