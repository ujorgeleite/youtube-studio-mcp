"""Key/value JSON cache with TTL, backed by stdlib sqlite3."""

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, path: Path | str, clock: Callable[[], float] = time.time):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, stored_at REAL NOT NULL)"
        )
        self._clock = clock

    def get(self, key: str, ttl_seconds: float) -> Any | None:
        row = self._conn.execute("SELECT value, stored_at FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or self._clock() - row[1] > ttl_seconds:
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, stored_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), self._clock()),
            )
