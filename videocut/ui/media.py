"""Arquivos locais servidos ao navegador por chave opaca, nunca por caminho."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app

REGISTRY: dict[str, str] = {}
MEDIA_TYPES = {".lrf": "video/mp4", ".mov": "video/mp4", ".m4v": "video/mp4"}


def media_url(path: str | Path) -> str:
    resolved = str(Path(path).resolve())
    key = hashlib.sha256(resolved.encode()).hexdigest()[:24]
    REGISTRY[key] = resolved
    return f"/media/{key}{Path(resolved).suffix.lower()}"


def media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return MEDIA_TYPES.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"


@app.get("/media/{name}")
def serve_media(name: str):
    path = REGISTRY.get(name.split(".", 1)[0])
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type=media_type(path))
