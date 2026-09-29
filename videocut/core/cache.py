from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .serial import read_json, write_json


def source_key(path: str | Path) -> str:
    source = Path(path).resolve()
    stat = source.stat()
    value = f"{source}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def fingerprint(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:12]


class StageCache:
    """Cache JSON por arquivo e etapa.

    `variant` separa resultados que dependem de modelo ou prompt, para que trocar
    o 4B pelo 8B não reaproveite descrições antigas.
    """

    def __init__(self, root: str | Path, source: str | Path):
        self.root = Path(root) / source_key(source)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, stage: str, variant: str = "") -> Path:
        return self.root / (f"{stage}__{variant}.json" if variant else f"{stage}.json")

    def load(self, stage: str, variant: str = "") -> Any | None:
        return read_json(self.path(stage, variant))

    def save(self, stage: str, value: Any, variant: str = "") -> Path:
        return write_json(self.path(stage, variant), value)
