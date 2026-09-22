from __future__ import annotations

import subprocess
import sys


def choose_directory(prompt: str = "Selecione a pasta de clipes") -> str | None:
    if sys.platform == "darwin":
        safe = prompt.replace('"', "'")
        result = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{safe}")'], capture_output=True, text=True)
        return result.stdout.strip() or None
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk(); root.withdraw()
        chosen = filedialog.askdirectory(title=prompt)
        root.destroy()
        return chosen or None
    except ImportError:
        return None
