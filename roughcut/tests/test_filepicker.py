"""Testa o parsing do seletor de pasta no macOS — sem abrir diálogo real."""

from __future__ import annotations

import os
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cockpit import filepicker  # noqa: E402


def _fake_run(stdout: str):
    def run(cmd, capture_output, text):
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    return run


def test_macos_choose_returns_trimmed_path(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("/Users/g/clipes\n"))

    assert filepicker._macos_choose("prompt") == "/Users/g/clipes"


def test_macos_choose_cancel_returns_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(""))

    assert filepicker._macos_choose("prompt") is None


def test_macos_choose_handles_missing_osascript(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("no osascript")

    monkeypatch.setattr(subprocess, "run", boom)

    assert filepicker._macos_choose("prompt") is None
