"""Local paths and settings, overridable via environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    client_secret_file: Path
    token_file: Path
    cache_file: Path
    cache_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("YTS_DATA_DIR", Path.home() / ".youtube-studio-mcp"))
        return cls(
            data_dir=data_dir,
            client_secret_file=Path(os.environ.get("YTS_CLIENT_SECRET", data_dir / "client_secret.json")),
            token_file=data_dir / "token.json",
            cache_file=data_dir / "cache.db",
            cache_ttl_seconds=int(os.environ.get("YTS_CACHE_TTL", "3600")),
        )
