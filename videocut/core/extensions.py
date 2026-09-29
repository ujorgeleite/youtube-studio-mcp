"""Skills e agentes: arquivos Markdown com frontmatter, padrão no repo e do usuário em `.state/ajustes/`.

Skill muda como uma etapa existente pensa (texto acrescentado ao prompt).
Agente é uma etapa extra que lê a proposta e devolve texto; nunca altera a montagem.
O frontmatter segue o `SKILL.md` do Claude Code (`name`, `description`) com campos próprios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .settings import OVERRIDES, ROOT

SKILL_STAGES = ("capitulos", "capitulo")
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
SLUG = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True)
class Extension:
    key: str
    name: str
    description: str
    body: str
    path: Path
    builtin: bool
    stages: tuple[str, ...] = ()
    meta: dict = field(default_factory=dict, compare=False, hash=False)


def slugify(text: str) -> str:
    return SLUG.sub("-", text.lower()).strip("-") or "sem-nome"


def parse(path: Path, builtin: bool) -> Extension:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    meta = (yaml.safe_load(match.group(1)) or {}) if match else {}
    body = (match.group(2) if match else text).strip()
    stages = meta.get("etapas") or meta.get("etapa") or []
    stages = tuple([stages] if isinstance(stages, str) else stages)
    return Extension(path.stem, str(meta.get("name") or path.stem), str(meta.get("description") or ""), body, path, builtin,
                     stages, meta)


def render(name: str, description: str, body: str, **extra: object) -> str:
    meta = {"name": name, "description": description, **{key: value for key, value in extra.items() if value}}
    return f"---\n{yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()}\n---\n\n{body.strip()}\n"


class Registry:
    def __init__(self, kind: str):
        self.kind = kind
        self.builtin_dir = ROOT / kind
        self.user_dir = OVERRIDES / kind

    def all(self) -> list[Extension]:
        found: dict[str, Extension] = {}
        for folder, builtin in ((self.builtin_dir, True), (self.user_dir, False)):
            for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
                found[path.stem] = parse(path, builtin)
        return sorted(found.values(), key=lambda item: item.name.lower())

    def get(self, key: str) -> Extension | None:
        return next((item for item in self.all() if item.key == key), None)

    def save(self, name: str, description: str, body: str, key: str | None = None, **extra: object) -> Extension:
        """Salva na pasta do usuário; editar uma padrão cria a versão do usuário com a mesma chave."""
        if not name.strip() or not body.strip():
            raise ValueError("nome e instruções são obrigatórios")
        target = self.user_dir / f"{key or slugify(name)}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(name.strip(), description.strip(), body, **extra), encoding="utf-8")
        return parse(target, False)

    def remove(self, key: str) -> bool:
        """Só apaga a versão do usuário; a padrão do repositório volta a valer."""
        target = self.user_dir / f"{key}.md"
        if target.is_file():
            target.unlink()
            return True
        return False


SKILLS = Registry("skills")
AGENTS = Registry("agentes")


def skills_text(active: list[str], stage: str) -> str:
    chosen = [skill for skill in SKILLS.all() if skill.key in set(active) and (not skill.stages or stage in skill.stages)]
    if not chosen:
        return "(nenhuma skill ativa)"
    return "\n\n".join(f"### {skill.name}\n{skill.body}" for skill in chosen)
