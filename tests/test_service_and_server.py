import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from youtube_studio_mcp.auth import NotAuthenticatedError
from youtube_studio_mcp.cache import Cache
from youtube_studio_mcp.server import build_server
from youtube_studio_mcp.service import ChannelService, Services

OVERVIEW = {
    "channel_id": "UC123",
    "title": "My Channel",
    "subscriber_count": 1500,
    "view_count": 5000,
    "video_count": 42,
    "uploads_playlist_id": "UU123",
}

TOOL_NAMES = [
    "get_channel_overview",
    "get_channel_metrics",
    "list_videos",
    "get_retention_curve",
    "analyze_pillar_performance",
    "rank_video_efficiency",
]


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return OVERVIEW


def _channel_service(fetcher):
    return ChannelService(Cache(":memory:"), fetcher, ttl_seconds=3600)


def _services(fetcher):
    # Only the channel service is exercised here; the rest are wired at __main__.
    return Services(
        channel=_channel_service(fetcher), analytics=None, library=None, pillar=None, efficiency=None
    )


def test_service_uses_cache_unless_refresh():
    fetcher = FakeFetcher()
    service = _channel_service(fetcher)

    assert service.get_channel_overview() == OVERVIEW
    assert service.get_channel_overview() == OVERVIEW
    assert fetcher.calls == 1

    service.get_channel_overview(refresh=True)
    assert fetcher.calls == 2


def test_server_registers_all_five_tools():
    services = _services(FakeFetcher())
    server = build_server(lambda: services)

    async def run():
        tools = await server.list_tools()
        assert sorted(t.name for t in tools) == sorted(TOOL_NAMES)
        result = await server.call_tool("get_channel_overview", {})
        assert not result.is_error
        assert result.structured_content == OVERVIEW

    asyncio.run(run())


def test_server_surfaces_auth_error_message():
    def not_authenticated():
        raise NotAuthenticatedError("Not authenticated. Run: youtube-studio-mcp auth")

    server = build_server(not_authenticated)

    # Direct call_tool raises; the protocol handler turns ToolError into an is_error result.
    with pytest.raises(ToolError, match="youtube-studio-mcp auth"):
        asyncio.run(server.call_tool("get_channel_overview", {}))
