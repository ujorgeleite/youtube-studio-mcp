"""Modo offline: o app carrega modelos só do disco e nunca acessa a rede.

Precisa rodar antes do primeiro import de `huggingface_hub`, que lê as variáveis
de ambiente uma única vez. Downloads acontecem apenas em `analysis/models.py`,
num subprocesso que liga a rede explicitamente.
"""

from __future__ import annotations

import os

OFFLINE_VARIABLES = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}


def enable_offline() -> None:
    for key, value in OFFLINE_VARIABLES.items():
        os.environ[key] = value


def online_environment() -> dict[str, str]:
    environment = {**os.environ, "HF_HUB_DISABLE_XET": "1", "HF_HUB_DOWNLOAD_TIMEOUT": "30", "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        environment[key] = "0"
    return environment
