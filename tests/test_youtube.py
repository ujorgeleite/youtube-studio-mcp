import pytest

from youtube_studio_mcp.youtube import parse_channel_overview


def _response(**stats):
    return {
        "items": [
            {
                "id": "UC123",
                "snippet": {"title": "My Channel"},
                "statistics": {"viewCount": "5000", "videoCount": "42", **stats},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
            }
        ]
    }


def test_parses_api_strings_into_ints():
    assert parse_channel_overview(_response(subscriberCount="1500")) == {
        "channel_id": "UC123",
        "title": "My Channel",
        "subscriber_count": 1500,
        "view_count": 5000,
        "video_count": 42,
        "uploads_playlist_id": "UU123",
    }


def test_hidden_subscriber_count_is_none():
    assert parse_channel_overview(_response(hiddenSubscriberCount=True))["subscriber_count"] is None


def test_no_channel_raises():
    with pytest.raises(LookupError):
        parse_channel_overview({"items": []})
