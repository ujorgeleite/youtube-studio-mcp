from smartcut.cache import StageCache, source_key


def test_stage_cache_is_stable_for_same_source_and_independent_per_stage(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    cache = StageCache(tmp_path / "cache", source)
    cache.save("vad", {"speech": []})
    cache.save("transcript", {"words": []})

    assert source_key(source) == source_key(source)
    assert cache.load("vad") == {"speech": []}
    assert cache.load("transcript") == {"words": []}
