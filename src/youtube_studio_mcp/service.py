"""Use cases: combine the API client with the cache. No MCP or Google imports here."""

from collections.abc import Callable

from .cache import Cache
from .youtube import ChannelOverview

CHANNEL_OVERVIEW_KEY = "channel_overview:mine"


class ChannelService:
    def __init__(self, cache: Cache, fetch_overview: Callable[[], ChannelOverview], ttl_seconds: int):
        self._cache = cache
        self._fetch_overview = fetch_overview
        self._ttl = ttl_seconds

    def get_channel_overview(self, refresh: bool = False) -> ChannelOverview:
        if not refresh and (cached := self._cache.get(CHANNEL_OVERVIEW_KEY, self._ttl)) is not None:
            return cached
        overview = self._fetch_overview()
        self._cache.set(CHANNEL_OVERVIEW_KEY, overview)
        return overview
