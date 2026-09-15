"""Testa o passo 1 (transcribe) — só a FORMATAÇÃO, a partir de Whisper mockado.

Não baixa modelo nem processa áudio (lento/pesado). Mocka a saída do Whisper e
verifica que o transcript sai no formato que o passo 2 consome.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps import transcribe  # noqa: E402
from steps.transcribe import format_transcript  # noqa: E402


def test_format_transcript_shape():
    segments = [
        {"start": 0.0, "end": 5.2, "text": " olá pessoal "},
        {"start": 5.2, "end": 11.0, "text": "hoje vamos falar"},
    ]
    out = format_transcript("C01", "intro.mp4", segments)
    lines = out.splitlines()

    assert lines[0] == "[C01] arquivo=intro.mp4"
    assert lines[1] == "00:00:00–00:00:05 olá pessoal"
    assert lines[2] == "00:00:05–00:00:11 hoje vamos falar"


def test_format_transcript_empty_segments():
    out = format_transcript("C09", "vazio.mp4", [])
    assert out == "[C09] arquivo=vazio.mp4"


def test_transcribe_clip_uses_whisper_output(monkeypatch):
    monkeypatch.setattr(
        transcribe,
        "_run_whisper",
        lambda path, model_size: [{"start": 1.0, "end": 3.0, "text": "mock"}],
    )
    out = transcribe.transcribe_clip("/qualquer/C02.mp4", "C02")
    assert out == "[C02] arquivo=C02.mp4\n00:00:01–00:00:03 mock"


def test_transcribe_folder_concatenates(monkeypatch, tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.mov").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore")
    monkeypatch.setattr(
        transcribe,
        "_run_whisper",
        lambda path, model_size: [{"start": 0.0, "end": 2.0, "text": "t"}],
    )

    text, clip_map = transcribe.transcribe_folder(str(tmp_path))

    assert clip_map == {"C01": str(tmp_path / "a.mp4"), "C02": str(tmp_path / "b.mov")}
    assert "[C01] arquivo=a.mp4" in text
    assert "[C02] arquivo=b.mov" in text
    assert "\n\n" in text
