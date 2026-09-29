from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def models() -> dict:
    return load_yaml("modelos.yaml")


def vision_options() -> dict[str, dict]:
    return models().get("vision", {}).get("options", {})


def vision_repo(name: str | None = None) -> str:
    options = vision_options()
    key = name or models().get("vision", {}).get("default", "")
    if key in options:
        return options[key]["repo"]
    return key


def sampling() -> dict:
    return models().get("sampling", {})


def glossary() -> dict:
    return load_yaml("glossario.yaml")
