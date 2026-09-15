"""Load the hand-maintained videoId -> pillar map (config/pilares.json)."""

import json
from pathlib import Path


def load_pillars(path: Path | str) -> dict:
    """Return the videoId -> {pilar, formato, seo} map; a missing file means nothing
    is classified yet, not an error."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())
