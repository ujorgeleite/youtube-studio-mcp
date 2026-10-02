from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .settings import resolve

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    path = resolve(name, CONFIG_DIR)
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


def model_cached(repo: str) -> bool:
    return (HF_CACHE / f"models--{repo.replace('/', '--')}").is_dir()


def sampling() -> dict:
    return models().get("sampling", {})


def min_take_s() -> float:
    return float(models().get("material", {}).get("min_take_s", 5))


def glossary() -> dict:
    return load_yaml("glossario.yaml")
