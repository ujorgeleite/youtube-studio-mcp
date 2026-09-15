from youtube_studio_mcp.cache import Cache


def test_returns_value_within_ttl_and_expires_after():
    now = [1000.0]
    cache = Cache(":memory:", clock=lambda: now[0])
    cache.set("k", {"a": 1})

    assert cache.get("k", ttl_seconds=60) == {"a": 1}
    now[0] += 61
    assert cache.get("k", ttl_seconds=60) is None


def test_missing_key_returns_none():
    assert Cache(":memory:").get("nope", ttl_seconds=60) is None


def test_persists_on_disk(tmp_path):
    Cache(tmp_path / "c.db").set("k", [1, 2])
    assert Cache(tmp_path / "c.db").get("k", ttl_seconds=60) == [1, 2]
