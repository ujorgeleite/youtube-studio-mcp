"""Extrai JSON da resposta de modelos locais, que às vezes cercam o objeto com texto."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class JsonTextError(ValueError):
    pass


def _balanced(text: str, start: int) -> str | None:
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            escaped = char == "\\" and not escaped
            if char == '"' and not escaped:
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _candidates(text: str) -> list[str]:
    found = [match.strip() for match in _FENCE.findall(text)]
    for index, char in enumerate(text):
        if char in "{[":
            block = _balanced(text, index)
            if block:
                found.append(block)
                break
    return found


def parse_json(text: str) -> Any:
    for candidate in _candidates(text):
        for attempt in (candidate, _TRAILING_COMMA.sub(r"\1", candidate)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    raise JsonTextError(f"resposta sem JSON válido: {text[:160]!r}")
