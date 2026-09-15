"""Entry point. See `youtube-studio-mcp --help`.

Without a command: interactive shell in a terminal, MCP server (stdio) otherwise.
"""

import sys
from functools import cache

from . import auth
from .cache import Cache
from .cli import build_parser, run_command
from .config import Settings
from .server import build_server
from .service import ChannelService
from .shell import Shell
from .youtube import YouTubeClient


def build_service(settings: Settings) -> ChannelService:
    client = YouTubeClient(auth.load_credentials(settings))
    return ChannelService(Cache(settings.cache_file), client.fetch_channel_overview, settings.cache_ttl_seconds)


def main(argv: list[str] | None = None) -> None:
    parser, commands = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    get_service = cache(lambda: build_service(settings))  # exceptions aren't cached, so auth can be retried
    command = args.command or ("shell" if sys.stdin.isatty() else "serve")

    if command == "serve":
        build_server(get_service).run("stdio")
    elif command == "shell":
        try:
            Shell(parser, commands, lambda a: run_command(a, settings, get_service)).cmdloop()
        except KeyboardInterrupt:
            print()
    elif code := run_command(args, settings, get_service):
        sys.exit(code)


if __name__ == "__main__":
    main()
