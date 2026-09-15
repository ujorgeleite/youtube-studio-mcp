import json

import pytest

from youtube_studio_mcp import __main__ as cli
from youtube_studio_mcp.auth import NotAuthenticatedError
from youtube_studio_mcp.cache import Cache
from youtube_studio_mcp.service import ChannelService, Services

OVERVIEW = {"channel_id": "UC123", "title": "My Channel", "subscriber_count": 1500,
            "view_count": 5000, "video_count": 42, "uploads_playlist_id": "UU123"}


def test_overview_prints_json(monkeypatch, capsys):
    channel = ChannelService(Cache(":memory:"), lambda: OVERVIEW, ttl_seconds=3600)
    services = Services(channel=channel, analytics=None, library=None, pillar=None, efficiency=None)
    monkeypatch.setattr(cli, "build_services", lambda settings: services)

    cli.main(["overview", "--refresh"])

    assert json.loads(capsys.readouterr().out) == OVERVIEW


def test_overview_without_auth_exits_with_message(monkeypatch, capsys):
    def not_authenticated(settings):
        raise NotAuthenticatedError("Not authenticated. Run: youtube-studio-mcp auth")

    monkeypatch.setattr(cli, "build_services", not_authenticated)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["overview"])

    assert exit_info.value.code == 1
    assert "youtube-studio-mcp auth" in capsys.readouterr().err
