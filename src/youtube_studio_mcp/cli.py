"""Command definitions shared by the one-shot CLI and the interactive shell."""

import argparse
import json
import sys
from collections.abc import Callable

from googleapiclient.errors import HttpError

from . import auth
from .config import Settings
from .service import Services

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

    metrics = add("metrics", "channel Analytics metrics for a date range (default last 28 days)")
    metrics.add_argument("--start", help="start date YYYY-MM-DD")
    metrics.add_argument("--end", help="end date YYYY-MM-DD")
    metrics.add_argument("--refresh", action="store_true", help="bypass the local cache")

    videos = add("videos", "list every uploaded video (id, title, date, duration)")
    videos.add_argument("--refresh", action="store_true", help="bypass the local cache")

    retention = add("retention", "audience retention curve for one video")
    retention.add_argument("video_id", help="the YouTube video id")
    retention.add_argument("--refresh", action="store_true", help="bypass the local cache")

    pillars = add("pillars", "watch time and retention grouped and ranked by content pillar")
    pillars.add_argument("--start", help="start date YYYY-MM-DD")
    pillars.add_argument("--end", help="end date YYYY-MM-DD")

    return parser, commands


def run_command(args: argparse.Namespace, settings: Settings, get_services: Callable[[], Services]) -> int:
    """Run a non-server command. Returns the process exit code."""
    try:
        if args.command == "auth":
            auth.login(settings)
            print(f"Authenticated. Token saved to {settings.token_file}")
        elif args.command == "overview":
            _print_json(get_services().channel.get_channel_overview(refresh=args.refresh))
        elif args.command == "metrics":
            _print_json(get_services().analytics.get_channel_metrics(args.start, args.end, args.refresh))
        elif args.command == "videos":
            _print_json(get_services().library.list_videos(refresh=args.refresh))
        elif args.command == "retention":
            _print_json(get_services().analytics.get_retention_curve(args.video_id, refresh=args.refresh))
        elif args.command == "pillars":
            _print_json(get_services().pillar.analyze(args.start, args.end))
    except EXPECTED_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))
