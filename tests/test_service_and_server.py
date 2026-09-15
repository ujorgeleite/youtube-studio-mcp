import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from youtube_studio_mcp.auth import NotAuthenticatedError
from youtube_studio_mcp.cache import Cache
from youtube_studio_mcp.server import build_server
from youtube_studio_mcp.service import ChannelService

OVERVIEW = {
    "channel_id": "UC123",
    "title": "My Channel",
    "subscriber_count": 1500,
    "view_count": 5000,
    "video_count": 42,
    "uploads_playlist_id": "UU123",
}


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return OVERVIEW


def _service(fetcher):
    return ChannelService(Cache(":memory:"), fetcher, ttl_seconds=3600)


def test_service_uses_cache_unless_refresh():
    fetcher = FakeFetcher()
    service = _service(fetcher)

    assert service.get_channel_overview() == OVERVIEW
    assert service.get_channel_overview() == OVERVIEW
    assert fetcher.calls == 1

    service.get_channel_overview(refresh=True)
    assert fetcher.calls == 2


def test_server_exposes_tool_end_to_end():
    service = _service(FakeFetcher())
    server = build_server(lambda: service)

    async def run():
        tools = await server.list_tools()
        assert [t.name for t in tools] == ["get_channel_overview"]
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
