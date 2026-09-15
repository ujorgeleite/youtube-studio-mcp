"""Passo 2 — order: chama o LLM para ordenar os trechos numa cut-list.

NÃO-DETERMINÍSTICO: depende do LLM. Por isso não tem teste de QUALIDADE — a
qualidade da ordenação o usuário valida rodando. Os testes cobrem só o parsing
(com o cliente do LLM mockado).

O cliente do LLM fica atrás de `_call_llm`, uma função substituível/mockável.
O prompt vive em prompts/ordenacao.md (o "cérebro"), isolado do código.
"""

from __future__ import annotations

import json
import re

import yaml

DEFAULT_MODEL = "claude-opus-5"


class OrderError(RuntimeError):
    pass


def load_prompt_template(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load_format(path: str) -> str:
    """Lê o YAML do formato, valida que faz parse e devolve o texto para injeção."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    yaml.safe_load(text)  # valida; erro sobe como YAMLError
    return text


def build_prompt(template: str, format_yaml: str, transcripts: str) -> str:
    return template.replace("{FORMATO}", format_yaml).replace(
        "{TRANSCRIPTS}", transcripts
    )


def parse_cut_list(raw: str) -> dict:
    """Extrai o cut-list JSON da saída do LLM, tolerante a cercas ```."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    else:
        brace = text.find("{")
        if brace > 0:
            text = text[brace:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OrderError(f"saída do LLM não é JSON válido: {exc}") from exc
    if not isinstance(data, dict) or "roughcut" not in data:
        raise OrderError("JSON do LLM não tem a chave 'roughcut'")
    return data


def _call_llm(prompt: str) -> str:
    """Chamada real ao LLM (Anthropic). Substituível/mockável nos testes."""
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    return "".join(b.text for b in message.content if b.type == "text")


def order(
    transcripts: str,
    format_path: str,
    prompt_path: str,
    llm=None,
) -> dict:
    """Monta a cut-list a partir dos transcripts e do formato.

    `llm` é uma função (prompt: str) -> str; se None, usa o cliente real.
    """
    template = load_prompt_template(prompt_path)
    format_yaml = load_format(format_path)
    prompt = build_prompt(template, format_yaml, transcripts)
    call = llm or _call_llm
    return parse_cut_list(call(prompt))
