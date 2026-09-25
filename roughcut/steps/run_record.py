"""Registro de execução: cada run vira um bundle autocontido em runs/<stamp>__<slug>/.

O objetivo é alimentar uma IA em loops futuros de melhoria, então tudo o que
importa para reproduzir e criticar um run fica no bundle: manifesto (run.json),
log estruturado append-only (events.jsonl) e os artefatos de cada passo
(transcripts, prompt do LLM, resposta crua, cut-list, crítica, saída).

Sem dependências pesadas e sem imports do pipeline — é substituível/mockável e os
testes cobrem toda a camada sem rede, sem LLM e sem Whisper.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "-" for c in text.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "run"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _probe_first_line(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0].strip() if output else None


def _environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ffmpeg": _probe_first_line(["ffmpeg", "-version"]),
        "git_sha": _probe_first_line(["git", "rev-parse", "--short", "HEAD"]),
    }


class RunRecord:
    def __init__(
        self,
        directory: Path,
        params: dict[str, Any],
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utcnow,
        environment: Callable[[], dict[str, Any]] = _environment,
    ):
        self._dir = directory
        self._events_file = directory / "events.jsonl"
        self._clock = clock
        self._now = now
        self._environment = environment
        self._params = dict(params)
        self._created_at = now()
        self._start = clock()
        self._env: dict[str, Any] | None = None
        self._steps: list[dict[str, Any]] = []
        self._artifacts: dict[str, str] = {}

    @classmethod
    def create(cls, runs_root: str | Path, params: dict[str, Any], **kwargs: Any) -> "RunRecord":
        root = Path(runs_root)
        stamp = _utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        label = _slug(str(params.get("format") or params.get("mode") or "run"))
        directory = root / f"{stamp}__{label}"
        suffix = 1
        while directory.exists():
            suffix += 1
            directory = root / f"{stamp}__{label}-{suffix}"
        directory.mkdir(parents=True, exist_ok=True)

        record = cls(directory, params, **kwargs)
        record.event("run", "start", params=record._params, environment=record.environment())
        return record

    @property
    def dir(self) -> Path:
        return self._dir

    def environment(self) -> dict[str, Any]:
        if self._env is None:
            self._env = self._environment()
        return self._env

    def event(self, step: str, event: str, level: str = "info", **payload: Any) -> None:
        line = {
            "ts": self._now().isoformat(),
            "elapsed_ms": self._elapsed_ms(),
            "step": step,
            "event": event,
            "level": level,
            "payload": payload,
        }
        with self._events_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    @contextmanager
    def step(self, name: str, **start_payload: Any):
        self.event(name, "step_start", **start_payload)
        started = self._clock()
        try:
            yield
        except Exception as exc:
            self._record_step(name, "error", started)
            self.event(
                name,
                "step_error",
                level="error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        else:
            self._record_step(name, "ok", started)
            self.event(name, "step_end", duration_ms=self._steps[-1]["duration_ms"])

    def artifact(self, name: str, content: Any, *, filename: str | None = None) -> Path:
        relative = filename or name
        path = self._dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        elif isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding="utf-8")
        self._artifacts[name] = relative
        self.event("artifact", "written", name=name, path=relative)
        return path

    def note_output(self, name: str, path: str | Path) -> None:
        self._artifacts[name] = str(path)
        self.event("artifact", "output", name=name, path=str(path))

    def finalize(self, status: str = "ok", error: str | None = None) -> Path:
        manifest = {
            "run_id": self._dir.name,
            "status": status,
            "created_at": self._created_at.isoformat(),
            "finished_at": self._now().isoformat(),
            "duration_ms": self._elapsed_ms(),
            "params": self._params,
            "environment": self.environment(),
            "steps": self._steps,
            "artifacts": self._artifacts,
            "error": error,
        }
        manifest_path = self._dir / "run.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.event("run", "finalize", status=status, error=error)
        return manifest_path

    def _elapsed_ms(self) -> int:
        return round((self._clock() - self._start) * 1000)

    def _record_step(self, name: str, status: str, started: float) -> None:
        self._steps.append(
            {"step": name, "status": status, "duration_ms": round((self._clock() - started) * 1000)}
        )
