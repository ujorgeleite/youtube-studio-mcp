from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "config" / "presets.yaml"
GLOSSARY_PATH = ROOT / "config" / "glossario.yaml"


@dataclass(frozen=True)
class CutRules:
    pause_within_sentence_s: float
    pause_after_sentence_s: float
    breath_padding_s: float
    min_segment_s: float
    audio_crossfade_ms: int
    preserve_dramatic_pauses: bool
    punch_in: bool


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"configuração inválida: {path}")
    return data


def list_presets(path: Path = PRESETS_PATH) -> list[str]:
    return sorted(_load_yaml(path))


def load_rules(name: str, path: Path = PRESETS_PATH) -> CutRules:
    presets = _load_yaml(path)
    if name not in presets:
        raise ValueError(f"preset não encontrado: {name}")
    return CutRules(**presets[name])


def load_glossary(path: Path = GLOSSARY_PATH) -> dict:
    data = _load_yaml(path)
    corrections = data.get("corrections") or {}
    if not isinstance(corrections, dict):
        raise ValueError("corrections deve ser um mapa")
    return data


def apply_glossary(text: str, corrections: dict[str, str]) -> str:
    result = text
    for wrong, right in corrections.items():
        result = result.replace(wrong, right).replace(wrong.capitalize(), right)
    return result
