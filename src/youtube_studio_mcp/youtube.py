"""Thin YouTube Data API v3 client."""

from typing import TypedDict

from googleapiclient.discovery import build


class ChannelOverview(TypedDict):
    channel_id: str
    title: str
    subscriber_count: int | None  # None when the channel hides it
    view_count: int
    video_count: int
    uploads_playlist_id: str


class VideoSummary(TypedDict):
    id: str
    title: str
    published_at: str
    duration: str


class YouTubeClient:
    def __init__(self, credentials):
        self._api = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def fetch_channel_overview(self) -> ChannelOverview:
        response = self._api.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
        return parse_channel_overview(response)

    def list_uploads(self, uploads_playlist_id: str) -> list[VideoSummary]:
        """Every uploaded video via the uploads playlist, paginated; durations from a
        batched videos.list. Never uses search.list."""
        items: list[dict] = []
        page_token = None
        while True:
            response = (
                self._api.playlistItems()
                .list(
                    part="snippet,contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
            items.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        base = parse_playlist_items(items)
        durations = self._fetch_durations([v["id"] for v in base])
        for video in base:
            video["duration"] = durations.get(video["id"], "")
        return base

    def _fetch_durations(self, video_ids: list[str]) -> dict[str, str]:
        durations: dict[str, str] = {}
        for chunk in _chunked(video_ids, 50):
            response = self._api.videos().list(part="contentDetails", id=",".join(chunk)).execute()
            durations.update(parse_durations(response))
        return durations


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def parse_channel_overview(response: dict) -> ChannelOverview:
    items = response.get("items") or []
    if not items:
        raise LookupError("No YouTube channel found for the authenticated account.")
    item = items[0]
    stats = item["statistics"]
    hidden = stats.get("hiddenSubscriberCount", False)
    return ChannelOverview(
        channel_id=item["id"],
        title=item["snippet"]["title"],
        subscriber_count=None if hidden else int(stats.get("subscriberCount", 0)),
        view_count=int(stats.get("viewCount", 0)),
        video_count=int(stats.get("videoCount", 0)),
        uploads_playlist_id=item["contentDetails"]["relatedPlaylists"]["uploads"],
    )


def parse_playlist_items(items: list[dict]) -> list[VideoSummary]:
    videos: list[VideoSummary] = []
    for item in items:
        details = item.get("contentDetails", {})
        snippet = item.get("snippet", {})
        videos.append(
            VideoSummary(
                id=details.get("videoId") or snippet.get("resourceId", {}).get("videoId", ""),
                title=snippet.get("title", ""),
                published_at=details.get("videoPublishedAt", snippet.get("publishedAt", "")),
                duration="",
            )
        )
    return videos


def parse_durations(response: dict) -> dict[str, str]:
    return {item["id"]: item.get("contentDetails", {}).get("duration", "") for item in response.get("items", [])}
