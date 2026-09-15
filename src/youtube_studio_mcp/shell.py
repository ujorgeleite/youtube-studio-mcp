"""Interactive shell: a menu over the CLI commands, with Tab completion.

Commands are parsed by the same argparse parsers as the one-shot CLI, so
`overview --help` and `help overview` behave exactly like the terminal.
"""

import argparse
import cmd
import shlex
from collections.abc import Callable

COMMANDS = ("overview", "metrics", "videos", "retention", "pillars", "efficiency", "auth")  # serve/shell make no sense inside the shell
EXIT = ("exit", "quit")


class Shell(cmd.Cmd):
    intro = "YouTube Studio — 'help' lists commands, Tab completes, 'exit' quits."
    prompt = "yt> "

    def __init__(
        self,
        parser: argparse.ArgumentParser,
        commands: dict[str, argparse.ArgumentParser],
        run: Callable[[argparse.Namespace], int],
    ):
        super().__init__()
        self._parser = parser
        self._commands = commands
        self._run = run

    def preloop(self) -> None:
        try:
            import readline

            readline.set_completer_delims(" \t\n")  # keep "--flag" as one word
        except ImportError:
            pass

    def onecmd(self, line: str) -> bool:
        try:
            argv = shlex.split(line)
        except ValueError as exc:
            print(f"error: {exc}")
            return False
        if not argv:
            return False
        name = argv[0]
        if name == "EOF":  # Ctrl-D
            print()
            return True
        if name in EXIT:
            return True
        if name == "help":
            self._print_help(argv[1:])
            return False
        if name not in COMMANDS:
            print(f"unknown command: {name} (type 'help')")
            return False
        try:
            args = self._parser.parse_args(argv)
        except SystemExit:  # argparse already printed --help or the usage error
            return False
        self._run(args)
        return False

    def _print_help(self, topics: list[str]) -> None:
        if topics and topics[0] in COMMANDS:
            self._commands[topics[0]].print_help()
            return
        print("Commands:")
        for name in COMMANDS:
            print(f"  {name:<12}{self._commands[name].description}")
        print(f"  {'help [cmd]':<12}show help (or: <cmd> --help)")
        print(f"  {'exit':<12}quit the shell")

    def completenames(self, text: str, *ignored) -> list[str]:
        return [n for n in (*COMMANDS, "help", *EXIT) if n.startswith(text)]

    def complete_help(self, text: str, *ignored) -> list[str]:
        return [n for n in COMMANDS if n.startswith(text)]

    def completedefault(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        sub = self._commands.get(line.split()[0]) if line.split()[0] in COMMANDS else None
        if sub is None:
            return []
        flags = [flag for action in sub._actions for flag in action.option_strings]
        return [f for f in flags if f.startswith(text) and f not in line.split()]
