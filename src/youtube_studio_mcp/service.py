"""Use cases: combine the API clients with the cache. No MCP or Google imports here."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from .cache import Cache
from .config import (
    ANALYTICS_RECENT_TTL,
    ANALYTICS_STABLE_TTL,
    RECENT_WINDOW_DAYS,
    RETENTION_TTL,
    VIDEO_LIST_TTL,
)
from .youtube import ChannelOverview

CHANNEL_OVERVIEW_KEY = "channel_overview:mine"

_RETENTION_START = "2005-02-14"
_DEFAULT_WINDOW_DAYS = 28


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


class AnalyticsService:
    """Channel/video metrics and retention from the Analytics API, cached. Finished
    days use a long TTL; the still-settling recent window uses a short TTL."""

    def __init__(self, cache: Cache, client, today: Callable[[], date] = date.today):
        self._cache = cache
        self._client = client
        self._today = today

    def default_range(self) -> tuple[str, str]:
        end = self._today()
        start = end - timedelta(days=_DEFAULT_WINDOW_DAYS)
        return start.isoformat(), end.isoformat()

    def _ttl_for(self, end_date: str) -> int:
        days_old = (self._today() - date.fromisoformat(end_date)).days
        return ANALYTICS_RECENT_TTL if days_old <= RECENT_WINDOW_DAYS else ANALYTICS_STABLE_TTL

    def get_channel_metrics(
        self, start_date: str | None = None, end_date: str | None = None, refresh: bool = False
    ) -> dict:
        if not start_date or not end_date:
            start_date, end_date = self.default_range()
        raw = self._raw_metrics(f"channel_metrics:{start_date}:{end_date}", start_date, end_date, refresh)
        return format_channel_metrics(raw, start_date, end_date)

    def get_video_metrics(
        self, video_id: str, start_date: str, end_date: str, refresh: bool = False
    ) -> dict:
        key = f"video_metrics:{video_id}:{start_date}:{end_date}"
        return self._raw_metrics(key, start_date, end_date, refresh, video_id=video_id)

    def get_retention_curve(self, video_id: str, refresh: bool = False) -> dict:
        key = f"retention:{video_id}"
        points = None if refresh else self._cache.get(key, RETENTION_TTL)
        if points is None:
            points = self._client.fetch_retention_curve(video_id, _RETENTION_START, self._today().isoformat())
            self._cache.set(key, points)
        return {"video_id": video_id, "pontos": points}

    def _raw_metrics(self, key: str, start_date: str, end_date: str, refresh: bool, video_id: str | None = None):
        raw = None if refresh else self._cache.get(key, self._ttl_for(end_date))
        if raw is None:
            if video_id is None:
                raw = self._client.fetch_channel_metrics(start_date, end_date)
            else:
                raw = self._client.fetch_video_metrics(video_id, start_date, end_date)
            self._cache.set(key, raw)
        return raw


def format_channel_metrics(raw: dict, start_date: str, end_date: str) -> dict:
    return {
        "periodo": {"inicio": start_date, "fim": end_date},
        "exibicao": {
            "Visualizações": raw["views"],
            "Minutos assistidos": raw["estimatedMinutesWatched"],
            "Duração média (segundos)": raw["averageViewDuration"],
            "Inscritos ganhos": raw["subscribersGained"],
            "Inscritos perdidos": raw["subscribersLost"],
            "Inscritos líquidos": raw["subscribersNet"],
        },
        "raw": raw,
    }


class VideoLibraryService:
    def __init__(self, cache: Cache, list_videos: Callable[[str], list[dict]], overview: Callable[[], ChannelOverview]):
        self._cache = cache
        self._list_videos = list_videos
        self._overview = overview

    def list_videos(self, refresh: bool = False) -> dict:
        key = "video_library:mine"
        videos = None if refresh else self._cache.get(key, VIDEO_LIST_TTL)
        if videos is None:
            uploads = self._overview()["uploads_playlist_id"]
            videos = self._list_videos(uploads)
            self._cache.set(key, videos)
        return {"total": len(videos), "videos": videos}


class PillarService:
    """Derived aggregation over the cached video library and per-video metrics: group
    by mapped pillar and rank by watch time. No new API call."""

    UNCLASSIFIED = "não classificado"

    def __init__(
        self,
        list_videos: Callable[[], list[dict]],
        video_metrics: Callable[[str, str, str], dict],
        load_pillars: Callable[[], dict],
        default_range: Callable[[], tuple[str, str]],
    ):
        self._list_videos = list_videos
        self._video_metrics = video_metrics
        self._load_pillars = load_pillars
        self._default_range = default_range

    def analyze(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        if not start_date or not end_date:
            start_date, end_date = self._default_range()
        pillars = self._load_pillars()
        buckets: dict[str, dict] = {}
        for video in self._list_videos():
            vid = video["id"]
            name = pillars.get(vid, {}).get("pilar") or self.UNCLASSIFIED
            raw = self._video_metrics(vid, start_date, end_date)
            bucket = buckets.setdefault(name, {"pilar": name, "video_count": 0, "minutos_assistidos": 0, "_durations": []})
            bucket["video_count"] += 1
            bucket["minutos_assistidos"] += int(raw.get("estimatedMinutesWatched", 0) or 0)
            bucket["_durations"].append(int(raw.get("averageViewDuration", 0) or 0))

        ranking = []
        for bucket in buckets.values():
            durations = bucket.pop("_durations")
            bucket["retencao_media_segundos"] = round(sum(durations) / len(durations)) if durations else 0
            ranking.append(bucket)
        ranking.sort(key=lambda b: b["minutos_assistidos"], reverse=True)

        return {
            "periodo": {"inicio": start_date, "fim": end_date},
            "ranking": ranking,
            "videos_por_pilar": {b["pilar"]: b["video_count"] for b in ranking},
        }


@dataclass
class Services:
    channel: ChannelService
    analytics: AnalyticsService
    library: VideoLibraryService
    pillar: PillarService
