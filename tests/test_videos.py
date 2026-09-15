from youtube_studio_mcp.cache import Cache
from youtube_studio_mcp.service import VideoLibraryService
from youtube_studio_mcp.youtube import parse_durations, parse_playlist_items

PLAYLIST_ITEMS = [
    {
        "snippet": {"title": "Primeiro vídeo", "resourceId": {"videoId": "vid1"}},
        "contentDetails": {"videoId": "vid1", "videoPublishedAt": "2026-01-01T10:00:00Z"},
    },
    {
        "snippet": {"title": "Segundo vídeo", "resourceId": {"videoId": "vid2"}},
        "contentDetails": {"videoId": "vid2", "videoPublishedAt": "2026-02-01T10:00:00Z"},
    },
]

DURATIONS_RESPONSE = {
    "items": [
        {"id": "vid1", "contentDetails": {"duration": "PT10M5S"}},
        {"id": "vid2", "contentDetails": {"duration": "PT3M"}},
    ]
}


def test_parse_playlist_items_extracts_id_title_and_date():
    parsed = parse_playlist_items(PLAYLIST_ITEMS)
    assert [(v["id"], v["title"], v["published_at"]) for v in parsed] == [
        ("vid1", "Primeiro vídeo", "2026-01-01T10:00:00Z"),
        ("vid2", "Segundo vídeo", "2026-02-01T10:00:00Z"),
    ]


def test_parse_durations_maps_id_to_iso_duration():
    assert parse_durations(DURATIONS_RESPONSE) == {"vid1": "PT10M5S", "vid2": "PT3M"}


def test_library_lists_via_uploads_playlist_and_caches():
    calls = []
    videos = [{"id": "vid1", "title": "A", "published_at": "2026-01-01", "duration": "PT1M"}]

    def list_videos(uploads_playlist_id):
        calls.append(uploads_playlist_id)
        return videos

    overview = lambda: {"uploads_playlist_id": "UU123"}
    service = VideoLibraryService(Cache(":memory:"), list_videos, overview)

    result = service.list_videos()
    assert result == {"total": 1, "videos": videos}
    assert calls == ["UU123"]

    service.list_videos()  # served from cache, no second fetch
    assert calls == ["UU123"]

    service.list_videos(refresh=True)
    assert calls == ["UU123", "UU123"]
