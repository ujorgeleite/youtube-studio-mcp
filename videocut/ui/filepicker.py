from __future__ import annotations

import subprocess
import sys


def choose_directory(prompt: str = "Selecione a pasta com os takes") -> str | None:
    if sys.platform != "darwin":
        return None
    safe = prompt.replace('"', "'")
    result = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{safe}")'], capture_output=True, text=True)
    return result.stdout.strip() or None
