"""Motor multimodal local. O mesmo modelo atende a visão e o planejamento editorial."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Protocol

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
