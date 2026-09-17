"""Seletor de pasta nativo do SO (roda no servidor — a UI é local).

Um browser não expõe o caminho absoluto de uma pasta, então abrimos o diálogo
nativo: `osascript` no macOS, tkinter como fallback. É bloqueante — chame via
run.io_bound. Retorna None quando o usuário cancela ou não há diálogo disponível.
"""

from __future__ import annotations

import subprocess
import sys


def choose_directory(prompt: str = "Selecione a pasta de clipes") -> str | None:
    if sys.platform == "darwin":
        return _macos_choose(prompt)
    return _tk_choose(prompt)


def _macos_choose(prompt: str) -> str | None:
    safe = prompt.replace('"', "'")
    script = f'POSIX path of (choose folder with prompt "{safe}")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
    except OSError:
        return None
    return result.stdout.strip() or None


def _tk_choose(prompt: str) -> str | None:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        return None
    root = tkinter.Tk()
    root.withdraw()
    try:
        chosen = filedialog.askdirectory(title=prompt)
    finally:
        root.destroy()
    return chosen or None
