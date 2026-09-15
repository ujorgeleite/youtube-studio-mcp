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


class YouTubeClient:
    def __init__(self, credentials):
        self._api = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def fetch_channel_overview(self) -> ChannelOverview:
        response = self._api.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
        return parse_channel_overview(response)


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
