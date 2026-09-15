"""Testa o passo 2 (order) — só o PARSING, com o cliente do LLM mockado.

NÃO chama LLM real. O mock devolve a cut-list canônica; o teste verifica que
order.py injeta o prompt e faz parse do JSON no schema do passo 3.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.order import (  # noqa: E402
    OrderError,
    build_prompt,
    order,
    parse_cut_list,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMAT_PATH = os.path.join(ROOT, "formats", "qualidade-de-vida.yaml")
PROMPT_PATH = os.path.join(ROOT, "prompts", "ordenacao.md")
FIXTURE_CUT_LIST = os.path.join(ROOT, "tests", "fixtures", "cut_list.json")


def _canonical_cut_list_text() -> str:
    with open(FIXTURE_CUT_LIST, encoding="utf-8") as fh:
        return fh.read()


def test_parse_cut_list_with_json_fence():
    raw = "aqui está:\n```json\n{\"roughcut\": []}\n```\nfim"
    assert parse_cut_list(raw) == {"roughcut": []}


def test_parse_cut_list_plain_json():
    assert parse_cut_list('{"roughcut": [{"beat": "x", "clips": []}]}') == {
        "roughcut": [{"beat": "x", "clips": []}]
    }


def test_parse_cut_list_rejects_non_json():
    with pytest.raises(OrderError):
        parse_cut_list("desculpe, não consegui")


def test_parse_cut_list_rejects_missing_roughcut():
    with pytest.raises(OrderError):
        parse_cut_list('{"outra_coisa": []}')


def test_build_prompt_injects_markers():
    prompt = build_prompt(
        "FORMATO:\n{FORMATO}\nTRANSCRIPTS:\n{TRANSCRIPTS}", "F-DATA", "T-DATA"
    )
    assert "F-DATA" in prompt and "T-DATA" in prompt
    assert "{FORMATO}" not in prompt and "{TRANSCRIPTS}" not in prompt


def test_order_parses_mocked_llm_output():
    canonical = _canonical_cut_list_text()
    captured = {}

    def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return f"```json\n{canonical}\n```"

    result = order(
        "[C01] arquivo=a.mp4\n00:00:00–00:00:05 oi",
        FORMAT_PATH,
        PROMPT_PATH,
        llm=fake_llm,
    )

    assert result == json.loads(canonical)
    # o prompt real recebeu o formato e os transcripts injetados
    assert "qualidade-de-vida" in captured["prompt"]
    assert "[C01] arquivo=a.mp4" in captured["prompt"]
