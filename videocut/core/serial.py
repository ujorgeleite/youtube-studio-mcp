from __future__ import annotations

import dataclasses
import json
import types
import typing
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def to_data(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_data(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [to_data(item) for item in value]
    if isinstance(value, dict):
        return {key: to_data(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


def _convert(kind: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(kind)
    if origin in (typing.Union, types.UnionType):
        options = [option for option in typing.get_args(kind) if option is not type(None)]
        return _convert(options[0], value) if len(options) == 1 else value
    if origin is list:
        (item,) = typing.get_args(kind)
        return [_convert(item, entry) for entry in value]
    if origin is dict:
        _, item = typing.get_args(kind)
        return {key: _convert(item, entry) for key, entry in value.items()}
    if dataclasses.is_dataclass(kind):
        return from_data(kind, value)
    return value


def from_data(cls: type[T], data: dict) -> T:
    """Reconstrói dataclasses aninhadas; chaves desconhecidas são ignoradas."""
    hints = typing.get_type_hints(cls)
    names = {field.name for field in dataclasses.fields(cls)}
    return cls(**{key: _convert(hints[key], value) for key, value in data.items() if key in names})


def write_json(path: str | Path, value: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(to_data(value), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target


def read_json(path: str | Path) -> Any | None:
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8")) if source.is_file() else None
