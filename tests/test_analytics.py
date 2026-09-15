from datetime import date

from youtube_studio_mcp.analytics import parse_channel_metrics, parse_retention_curve
from youtube_studio_mcp.cache import Cache
from youtube_studio_mcp.config import ANALYTICS_RECENT_TTL, ANALYTICS_STABLE_TTL
from youtube_studio_mcp.service import AnalyticsService

# A canonical channel-metrics response (metrics only, so exactly one row).
CANONICAL_METRICS = {
    "kind": "youtubeAnalytics#resultTable",
    "columnHeaders": [
        {"name": "views", "dataType": "INTEGER"},
        {"name": "estimatedMinutesWatched", "dataType": "INTEGER"},
        {"name": "averageViewDuration", "dataType": "INTEGER"},
        {"name": "subscribersGained", "dataType": "INTEGER"},
        {"name": "subscribersLost", "dataType": "INTEGER"},
    ],
    "rows": [[1000, 5000, 300, 50, 8]],
}

CANONICAL_RETENTION = {
    "columnHeaders": [
        {"name": "elapsedVideoTimeRatio"},
        {"name": "audienceWatchRatio"},
        {"name": "relativeRetentionPerformance"},
    ],
    "rows": [[0.0, 1.0, 0.5], [1.0, 0.4, 0.7], [0.5, 0.6, 0.55]],
}


class FakeAnalyticsClient:
    def __init__(self):
        self.channel_calls = 0
        self.retention_calls = 0

    def fetch_channel_metrics(self, start_date, end_date):
        self.channel_calls += 1
        return parse_channel_metrics(CANONICAL_METRICS)

    def fetch_video_metrics(self, video_id, start_date, end_date):
        return parse_channel_metrics(CANONICAL_METRICS)

    def fetch_retention_curve(self, video_id, start_date, end_date):
        self.retention_calls += 1
        return parse_retention_curve(CANONICAL_RETENTION)


def test_parse_channel_metrics_computes_net_subscribers():
    assert parse_channel_metrics(CANONICAL_METRICS) == {
        "views": 1000,
        "estimatedMinutesWatched": 5000,
        "averageViewDuration": 300,
        "subscribersGained": 50,
        "subscribersLost": 8,
        "subscribersNet": 42,
    }


def test_parse_channel_metrics_empty_is_zeros():
    empty = {"columnHeaders": CANONICAL_METRICS["columnHeaders"], "rows": []}
    assert parse_channel_metrics(empty)["views"] == 0
    assert parse_channel_metrics(empty)["subscribersNet"] == 0


def test_get_channel_metrics_labels_and_caches():
    client = FakeAnalyticsClient()
    service = AnalyticsService(Cache(":memory:"), client, today=lambda: date(2026, 9, 15))

    result = service.get_channel_metrics("2026-08-01", "2026-08-28")
    assert result["periodo"] == {"inicio": "2026-08-01", "fim": "2026-08-28"}
    assert result["exibicao"]["Inscritos líquidos"] == 42
    assert result["raw"]["views"] == 1000

    service.get_channel_metrics("2026-08-01", "2026-08-28")  # served from cache
    assert client.channel_calls == 1

    service.get_channel_metrics("2026-08-01", "2026-08-28", refresh=True)
    assert client.channel_calls == 2


def test_default_range_is_last_28_days():
    service = AnalyticsService(Cache(":memory:"), FakeAnalyticsClient(), today=lambda: date(2026, 9, 15))
    assert service.default_range() == ("2026-08-18", "2026-09-15")


def test_recent_window_uses_short_ttl_stable_uses_long():
    service = AnalyticsService(Cache(":memory:"), FakeAnalyticsClient(), today=lambda: date(2026, 9, 15))
    # end date within the last ~3 days -> still settling -> short TTL
    assert service._ttl_for("2026-09-14") == ANALYTICS_RECENT_TTL
    # older finished window -> immutable -> long TTL
    assert service._ttl_for("2026-08-01") == ANALYTICS_STABLE_TTL


def test_parse_retention_curve_sorts_by_ratio():
    curve = parse_retention_curve(CANONICAL_RETENTION)
    assert [p["ratio"] for p in curve] == [0.0, 0.5, 1.0]
    assert curve[0] == {"ratio": 0.0, "watch_ratio": 1.0, "relative": 0.5}


def test_get_retention_curve_wraps_and_caches():
    client = FakeAnalyticsClient()
    service = AnalyticsService(Cache(":memory:"), client, today=lambda: date(2026, 9, 15))

    result = service.get_retention_curve("vid1")
    assert result["video_id"] == "vid1"
    assert len(result["pontos"]) == 3

    service.get_retention_curve("vid1")  # cached
    assert client.retention_calls == 1

    service.get_retention_curve("vid1", refresh=True)
    assert client.retention_calls == 2
