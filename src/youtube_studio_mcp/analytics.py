"""Thin YouTube Analytics API v2 client (separate service from the Data API)."""

from googleapiclient.discovery import build

CHANNEL_METRICS = "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost"
RETENTION_METRICS = "audienceWatchRatio,relativeRetentionPerformance"
EFFICIENCY_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "subscribersGained,subscribersLost,likes,comments"
)


class AnalyticsClient:
    def __init__(self, credentials):
        self._api = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)

    def _query(self, **params) -> dict:
        return self._api.reports().query(**params).execute()

    def fetch_channel_metrics(self, start_date: str, end_date: str) -> dict:
        response = self._query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=CHANNEL_METRICS,
        )
        return parse_channel_metrics(response)

    def fetch_video_metrics(self, video_id: str, start_date: str, end_date: str) -> dict:
        response = self._query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=CHANNEL_METRICS,
            filters=f"video=={video_id}",
        )
        return parse_channel_metrics(response)

    def fetch_video_efficiency(self, video_id: str, start_date: str, end_date: str) -> dict:
        response = self._query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=EFFICIENCY_METRICS,
            filters=f"video=={video_id}",
        )
        return parse_video_efficiency(response)

    def fetch_retention_curve(self, video_id: str, start_date: str, end_date: str) -> list[dict]:
        response = self._query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            dimensions="elapsedVideoTimeRatio",
            metrics=RETENTION_METRICS,
            filters=f"video=={video_id}",
        )
        return parse_retention_curve(response)


def _rows_as_dicts(response: dict) -> list[dict]:
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in (response.get("rows") or [])]


def _num(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parse_channel_metrics(response: dict) -> dict:
    """A metrics-only query returns at most one row; missing data yields zeros."""
    rows = _rows_as_dicts(response)
    row = rows[0] if rows else {}
    gained = int(row.get("subscribersGained", 0) or 0)
    lost = int(row.get("subscribersLost", 0) or 0)
    return {
        "views": int(row.get("views", 0) or 0),
        "estimatedMinutesWatched": int(row.get("estimatedMinutesWatched", 0) or 0),
        "averageViewDuration": int(row.get("averageViewDuration", 0) or 0),
        "subscribersGained": gained,
        "subscribersLost": lost,
        "subscribersNet": gained - lost,
    }


def parse_video_efficiency(response: dict) -> dict:
    """Per-video engagement metrics for the efficiency ranking; missing data zeroes."""
    rows = _rows_as_dicts(response)
    row = rows[0] if rows else {}
    gained = int(row.get("subscribersGained", 0) or 0)
    lost = int(row.get("subscribersLost", 0) or 0)
    return {
        "views": int(row.get("views", 0) or 0),
        "estimatedMinutesWatched": int(row.get("estimatedMinutesWatched", 0) or 0),
        "averageViewDuration": int(row.get("averageViewDuration", 0) or 0),
        "averageViewPercentage": float(row.get("averageViewPercentage", 0.0) or 0.0),
        "subscribersGained": gained,
        "subscribersLost": lost,
        "subscribersNet": gained - lost,
        "likes": int(row.get("likes", 0) or 0),
        "comments": int(row.get("comments", 0) or 0),
    }


def parse_retention_curve(response: dict) -> list[dict]:
    points = [
        {
            "ratio": _num(r.get("elapsedVideoTimeRatio")),
            "watch_ratio": _num(r.get("audienceWatchRatio")),
            "relative": _num(r.get("relativeRetentionPerformance")),
        }
        for r in _rows_as_dicts(response)
    ]
    points.sort(key=lambda p: p["ratio"] if p["ratio"] is not None else 0)
    return points
