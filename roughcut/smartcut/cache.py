from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def source_key(path: str | Path) -> str:
    source = Path(path).resolve()
    stat = source.stat()
    value = f"{source}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class StageCache:
    """Cache JSON por arquivo e etapa; regras mudam sem invalidar VAD/transcrição."""

    def __init__(self, root: str | Path, source: str | Path):
        self.root = Path(root) / source_key(source)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, stage: str) -> Path:
        return self.root / f"{stage}.json"

    def load(self, stage: str) -> Any | None:
        path = self.path(stage)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def save(self, stage: str, value: Any) -> Path:
        path = self.path(stage)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
