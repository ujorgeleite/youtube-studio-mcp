from __future__ import annotations

import hashlib
from pathlib import Path

from core.schema import Take

from .frames import extract_thumbnail
from .probe import MediaError, camera_proxy, list_videos, probe


def _thumb_name(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16] + ".jpg"


def catalog_take(index: int, path: Path, thumbnails: Path, previous: Take | None = None) -> Take:
    """Mantém o id já atribuído ao arquivo para não quebrar evidências antigas."""
    info = probe(path)
    proxy = camera_proxy(path, info.duration_s)
    thumb = thumbnails / _thumb_name(path)
    if not thumb.is_file():
        extract_thumbnail(proxy or path, thumb, info.duration_s)
    return Take(
        id=previous.id if previous else f"T{index:02d}",
        path=str(path.resolve()),
        name=path.name,
        duration_s=round(info.duration_s, 3),
        width=info.width,
        height=info.height,
        fps=info.fps,
        has_audio=info.has_audio,
        thumbnail=str(thumb),
        proxy=str(proxy.resolve()) if proxy else None,
    )


def next_take_index(known: list[Take]) -> int:
    numbers = [int(take.id[1:]) for take in known if take.id[1:].isdigit()]
    return max(numbers, default=0) + 1


def catalog_folder(folder: str | Path, thumbnails: Path, known: list[Take] | None = None) -> tuple[list[Take], dict[str, str]]:
    """Cataloga os vídeos da pasta; arquivos ilegíveis voltam em `failed` sem parar os demais."""
    by_path = {take.path: take for take in known or []}
    takes: list[Take] = []
    failed: dict[str, str] = {}
    counter = next_take_index(known or [])
    for path in list_videos(folder):
        previous = by_path.get(str(path.resolve()))
        try:
            takes.append(catalog_take(counter, path, thumbnails, previous))
        except MediaError as error:
            failed[path.name] = str(error)
            continue
        if previous is None:
            counter += 1
    return takes, failed
