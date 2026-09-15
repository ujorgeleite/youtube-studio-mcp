"""Entry point. See `youtube-studio-mcp --help`.

Without a command: interactive shell in a terminal, MCP server (stdio) otherwise.
"""

import sys
from functools import cache

from . import auth
from .analytics import AnalyticsClient
from .cache import Cache
from .cli import build_parser, run_command
from .config import Settings
from .pillars import load_pillars
from .server import build_server
from .service import (
    AnalyticsService,
    ChannelService,
    PillarService,
    Services,
    VideoLibraryService,
)
from .shell import Shell
from .youtube import YouTubeClient


def build_services(settings: Settings) -> Services:
    creds = auth.load_credentials(settings)
    data = YouTubeClient(creds)
    analytics_client = AnalyticsClient(creds)
    shared_cache = Cache(settings.cache_file)

    channel = ChannelService(shared_cache, data.fetch_channel_overview, settings.cache_ttl_seconds)
    analytics = AnalyticsService(shared_cache, analytics_client)
    library = VideoLibraryService(shared_cache, data.list_uploads, channel.get_channel_overview)
    pillar = PillarService(
        list_videos=lambda: library.list_videos()["videos"],
        video_metrics=analytics.get_video_metrics,
        load_pillars=lambda: load_pillars(settings.pillars_file),
        default_range=analytics.default_range,
    )
    return Services(channel=channel, analytics=analytics, library=library, pillar=pillar)


def main(argv: list[str] | None = None) -> None:
    parser, commands = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    get_services = cache(lambda: build_services(settings))  # exceptions aren't cached, so auth can be retried
    command = args.command or ("shell" if sys.stdin.isatty() else "serve")

    if command == "serve":
        build_server(get_services).run("stdio")
    elif command == "shell":
        try:
            Shell(parser, commands, lambda a: run_command(a, settings, get_services)).cmdloop()
        except KeyboardInterrupt:
            print()
    elif code := run_command(args, settings, get_services):
        sys.exit(code)


if __name__ == "__main__":
    main()
