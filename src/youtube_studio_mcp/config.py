"""Local paths and settings, overridable via environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

RECENT_WINDOW_DAYS = 3
ANALYTICS_RECENT_TTL = 60 * 60
ANALYTICS_STABLE_TTL = 60 * 60 * 24 * 30
VIDEO_LIST_TTL = 60 * 60 * 6
RETENTION_TTL = 60 * 60 * 24 * 30

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    client_secret_file: Path
    token_file: Path
    cache_file: Path
    cache_ttl_seconds: int
    pillars_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("YTS_DATA_DIR", Path.home() / ".youtube-studio-mcp"))
        return cls(
            data_dir=data_dir,
            client_secret_file=Path(os.environ.get("YTS_CLIENT_SECRET", data_dir / "client_secret.json")),
            token_file=data_dir / "token.json",
            cache_file=data_dir / "cache.db",
            cache_ttl_seconds=int(os.environ.get("YTS_CACHE_TTL", "3600")),
            pillars_file=Path(os.environ.get("YTS_PILLARS_FILE", _PROJECT_ROOT / "config" / "pilares.json")),
        )
