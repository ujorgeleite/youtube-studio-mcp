"""Motor multimodal local. O mesmo modelo atende a visão e o planejamento editorial."""

from __future__ import annotations

import gc
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from core.safety import ensure_writable

from .jsontext import JsonTextError, parse_json


class ModelError(RuntimeError):
    pass


class LocalModel(Protocol):
    name: str

    def generate(self, prompt: str, images: list[Path] | None = None, max_tokens: int = 700) -> str: ...

    def release(self) -> None: ...


def generate_json(model: LocalModel, prompt: str, images: list[Path] | None = None, *, max_tokens: int = 700, retries: int = 1) -> Any:
    """Uma nova tentativa com instrução explícita costuma corrigir JSON truncado ou cercado de texto."""
    last_error: Exception | None = None
    request = prompt
    for _ in range(retries + 1):
        text = model.generate(request, images, max_tokens)
        try:
            return parse_json(text)
        except JsonTextError as error:
            last_error = error
            request = prompt + "\n\nIMPORTANTE: responda somente com o JSON válido, sem texto antes ou depois."
    raise ModelError(str(last_error))


class ThermalGuardedModel:
    """Antes de cada chamada, espera o Mac esfriar se o modo de cargas longas estiver ligado."""

    def __init__(self, inner: LocalModel, governor):
        self.inner = inner
        self.governor = governor

    @property
    def name(self) -> str:
        return self.inner.name

    def generate(self, prompt: str, images: list[Path] | None = None, max_tokens: int = 700) -> str:
        self.governor.wait_if_hot()
        return self.inner.generate(prompt, images, max_tokens)

    def release(self) -> None:
        self.inner.release()


class RecordingModel:
    """Guarda cada pedido e resposta em JSONL: é o que se lê para ajustar prompts e regras."""

    def __init__(self, inner: LocalModel, log_file: Path, stage: Callable[[], str]):
        self.inner = inner
        self.log_file = log_file
        self.stage = stage

    @property
    def name(self) -> str:
        return self.inner.name

    def generate(self, prompt: str, images: list[Path] | None = None, max_tokens: int = 700) -> str:
        started = time.perf_counter()
        answer = self.inner.generate(prompt, images, max_tokens)
        record = {"hora": datetime.now().isoformat(timespec="seconds"), "etapa": self.stage(), "modelo": self.name,
                  "imagens": [Path(image).name for image in images or []], "segundos": round(time.perf_counter() - started, 2),
                  "prompt": prompt, "resposta": answer}
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with ensure_writable(self.log_file).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return answer

    def release(self) -> None:
        self.inner.release()


class MlxModel:
    def __init__(self, repo: str):
        self.name = repo
        self._model: Any = None
        self._processor: Any = None
        self._config: Any = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from mlx_vlm import load
        except ImportError as error:
            raise ModelError("mlx-vlm não instalado") from error
        self._model, self._processor = load(self.name)
        self._config = self._model.config

    def generate(self, prompt: str, images: list[Path] | None = None, max_tokens: int = 700) -> str:
        self._ensure_loaded()
        from mlx_vlm import apply_chat_template, generate

        paths = [str(path) for path in images or []]
        formatted = apply_chat_template(self._processor, self._config, prompt, num_images=len(paths))
        result = generate(
            self._model, self._processor, formatted, image=paths or None,
            max_tokens=max_tokens, temperature=0.0, verbose=False,
        )
        return getattr(result, "text", str(result))

    def release(self) -> None:
        self._model = self._processor = self._config = None
        gc.collect()
        try:
            import mlx.core as mx
            mx.clear_cache()
        except ImportError:
            pass
