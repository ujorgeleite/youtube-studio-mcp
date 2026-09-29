"""Proteção dos originais: nenhuma escrita, troca ou remoção pode atingir a pasta de origem.

Toda gravação do VideoCut passa por `ensure_writable`. Pastas de origem são
registradas ao abrir um projeto e ficam protegidas até o fim do processo.
"""

from __future__ import annotations

from pathlib import Path

_PROTECTED: set[Path] = set()


class SourceProtectionError(PermissionError):
    pass


def protect(folder: str | Path) -> Path:
    root = Path(folder).expanduser().resolve()
    _PROTECTED.add(root)
    return root


def protected_roots() -> frozenset[Path]:
    return frozenset(_PROTECTED)


def is_protected(path: str | Path) -> bool:
    """Links simbólicos são resolvidos: um atalho não contorna a proteção."""
    resolved = Path(path).expanduser().resolve()
    return any(resolved == root or root in resolved.parents for root in _PROTECTED)


def ensure_writable(path: str | Path) -> Path:
    target = Path(path)
    if is_protected(target):
        raise SourceProtectionError(f"escrita bloqueada: {target} fica dentro da pasta de origem, que o VideoCut nunca altera")
    return target


def write_text(path: str | Path, text: str) -> Path:
    target = ensure_writable(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
