"""MCP wiring: registers tools on an MCPServer (mcp>=2; formerly FastMCP)."""

import sys
from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .auth import NotAuthenticatedError
from .service import Services
from .youtube import ChannelOverview

_EXPECTED = (NotAuthenticatedError, LookupError)


def build_server(get_services: Callable[[], Services]) -> MCPServer:
    """get_services is called lazily so the server lists tools before auth."""
    server = MCPServer("youtube-studio")
    read_only = ToolAnnotations(readOnlyHint=True)

    def guard(fn):
        try:
            return fn()
        except _EXPECTED as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=read_only)
    def get_channel_overview(refresh: bool = False) -> ChannelOverview:
        """Basic stats of the authenticated owner's YouTube channel: subscribers,
        total views, video count and uploads playlist id. Cached locally; pass
        refresh=true to bypass the cache."""
        return guard(lambda: get_services().channel.get_channel_overview(refresh=refresh))

    @server.tool(annotations=read_only)
    def get_channel_metrics(
        start_date: str | None = None, end_date: str | None = None, refresh: bool = False
    ) -> dict:
        """Channel metrics from the YouTube Analytics API for a date range (default:
        last 28 days): views, minutes watched, average view duration, subscribers
        gained/lost and net. Dates are YYYY-MM-DD. Cached per range."""
        return guard(lambda: get_services().analytics.get_channel_metrics(start_date, end_date, refresh))

    @server.tool(annotations=read_only)
    def list_videos(refresh: bool = False) -> dict:
        """Every uploaded video (id, title, publish date, ISO-8601 duration) via the
        uploads playlist. Cached; pass refresh=true to bypass the cache."""
        return guard(lambda: get_services().library.list_videos(refresh=refresh))

    @server.tool(annotations=read_only)
    def get_retention_curve(video_id: str, refresh: bool = False) -> dict:
        """Audience retention curve for one video: a list of points
        {ratio, watch_ratio, relative} across the video's elapsed-time ratio."""
        return guard(lambda: get_services().analytics.get_retention_curve(video_id, refresh=refresh))

    @server.tool(annotations=read_only)
    def analyze_pillar_performance(start_date: str | None = None, end_date: str | None = None) -> dict:
        """Group each mapped video's watch time and retention by content pillar
        (config/pilares.json) and rank pillars by minutes watched. Unmapped videos
        land in a 'não classificado' bucket. Derived from cached metrics."""
        return guard(lambda: get_services().pillar.analyze(start_date, end_date))

    @server.tool(annotations=read_only)
    def rank_video_efficiency(start_date: str | None = None, end_date: str | None = None) -> dict:
        """Rank videos by efficiency within each format (longos vs shorts) over a date
        range. Efficiency criteria: retention (averageViewPercentage), subscribers
        gained, comments and likes. Returns every raw metric per video plus a
        transparent min-max score, so a downstream library can re-weight and decide."""
        return guard(lambda: get_services().efficiency.rank(start_date, end_date))

    return server


def _self_check() -> int:
    import asyncio

    def unavailable() -> Services:
        raise NotAuthenticatedError("self-check does not authenticate")

    server = build_server(unavailable)
    tools = asyncio.run(server.list_tools())
    print(f"{len(tools)} tools registered:")
    for tool in tools:
        print(f"  - {tool.name}")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(_self_check())
    print("Run the server via `youtube-studio-mcp serve`; use --self-check to list tools.", file=sys.stderr)
    sys.exit(2)
