from youtube_studio_mcp.cli import build_parser
from youtube_studio_mcp.shell import Shell


def _shell():
    parser, commands = build_parser()
    calls = []
    return Shell(parser, commands, lambda args: calls.append(args) or 0), calls


def test_runs_command_with_flags():
    shell, calls = _shell()

    assert shell.onecmd("overview --refresh") is False
    assert calls[0].command == "overview" and calls[0].refresh is True


def test_help_flag_and_help_command_do_not_exit(capsys):
    shell, calls = _shell()

    assert shell.onecmd("overview --help") is False
    assert shell.onecmd("help overview") is False
    assert shell.onecmd("help") is False
    assert calls == []
    assert capsys.readouterr().out.count("bypass the local cache") == 2  # once per help screen


def test_rejects_unknown_and_server_commands(capsys):
    shell, calls = _shell()

    shell.onecmd("serve")
    shell.onecmd("nope")
    assert calls == []
    assert "unknown command" in capsys.readouterr().out


def test_exit():
    shell, _ = _shell()
    assert shell.onecmd("exit") is True
    assert shell.onecmd("EOF") is True


def test_completion():
    shell, _ = _shell()

    assert shell.completenames("ov") == ["overview"]
    assert shell.complete_help("a") == ["auth"]
    assert shell.completedefault("--r", "overview --r", 9, 12) == ["--refresh"]
