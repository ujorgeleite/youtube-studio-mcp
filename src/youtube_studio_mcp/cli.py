"""Command definitions shared by the one-shot CLI and the interactive shell."""

import argparse
import json
import sys
from collections.abc import Callable

from googleapiclient.errors import HttpError

from . import auth
from .config import Settings
from .service import ChannelService

EXPECTED_ERRORS = (auth.NotAuthenticatedError, LookupError, FileNotFoundError, HttpError)


def build_parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    parser = argparse.ArgumentParser(
        prog="youtube-studio-mcp",
        description="YouTube Studio MCP server and CLI. Without a command it opens the "
        "interactive shell when run in a terminal, and the MCP server (stdio) otherwise.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    commands: dict[str, argparse.ArgumentParser] = {}

    def add(name: str, help: str) -> argparse.ArgumentParser:
        commands[name] = subparsers.add_parser(name, help=help, description=help)
        return commands[name]

    add("serve", "run the MCP server over stdio")
    add("shell", "interactive menu with Tab completion")
    add("auth", "log in with Google (opens the browser)")
    overview = add("overview", "channel subscribers, total views, video count, uploads playlist")
    overview.add_argument("--refresh", action="store_true", help="bypass the local cache")

    return parser, commands


def run_command(args: argparse.Namespace, settings: Settings, get_service: Callable[[], ChannelService]) -> int:
    """Run a non-server command. Returns the process exit code."""
    try:
        if args.command == "auth":
            auth.login(settings)
            print(f"Authenticated. Token saved to {settings.token_file}")
        elif args.command == "overview":
            _print_json(get_service().get_channel_overview(refresh=args.refresh))
    except EXPECTED_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))
