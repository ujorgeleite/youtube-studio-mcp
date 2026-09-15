"""MCP wiring: registers tools on an MCPServer (mcp>=2; formerly FastMCP)."""

from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .auth import NotAuthenticatedError
from .service import ChannelService
from .youtube import ChannelOverview


def build_server(get_service: Callable[[], ChannelService]) -> MCPServer:
    # get_service is called lazily so the server starts (and lists tools) even
    # before the user has authenticated.
    server = MCPServer("youtube-studio")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_channel_overview(refresh: bool = False) -> ChannelOverview:
        """Basic stats of the authenticated owner's YouTube channel: subscribers,
        total views, video count and uploads playlist id. Cached locally; pass
        refresh=true to bypass the cache."""
        try:
            return get_service().get_channel_overview(refresh=refresh)
        except (NotAuthenticatedError, LookupError) as exc:
            # ToolError messages reach the client; other exceptions are masked as crashes.
            raise ToolError(str(exc)) from exc

    return server
