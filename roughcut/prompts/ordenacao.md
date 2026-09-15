# Prompt de Ordenação (passo 2) — o "cérebro" do roughcut

> Este arquivo é o **cérebro** do pipeline e é aqui que se itera. Trocar o texto
> abaixo muda a qualidade da ordenação sem tocar em uma linha de código Python.
> Ele é injetado em `steps/order.py` via os marcadores `{FORMATO}` e `{TRANSCRIPTS}`.
>
> **PLACEHOLDER:** este é um prompt-base funcional. Substitua pelo cérebro real
> (ver o aviso no README) quando for validar a ordenação de verdade.

Você é um editor de vídeo assistente. Recebe (1) a definição de um FORMATO com seus
beats e (2) os TRANSCRIPTS timestampados dos clipes brutos. Sua tarefa é montar uma
**cut-list** que preenche os beats do formato com os melhores trechos dos clipes.

## FORMATO

{FORMATO}

## TRANSCRIPTS

{TRANSCRIPTS}

## Saída

Responda com **um único bloco JSON** (sem texto fora dele) neste schema exato:

```json
{
  "roughcut": [
    {
      "beat": "<id do beat do formato>",
      "clips": [
        { "clip_id": "C01", "in": "HH:MM:SS", "out": "HH:MM:SS" }
      ],
      "broll_suggestion": "<sugestão de B-roll, ou string vazia>"
    }
  ],
  "critica": {
    "gaps": ["<beats sem material bom>"],
    "redundancia": ["<trechos repetidos>"],
    "ordem": "<observações sobre a ordem escolhida>",
    "orfaos": ["<clip_ids/trechos que sobraram sem uso>"],
    "hook_candidates": ["<melhores trechos para o cold_open>"],
    "duracao_estimada_s": 0
  }
}
```

Regras:
- Para beats do tipo `broll_mudo`, deixe `clips` como `[]` e preencha `broll_suggestion`.
- `in`/`out` são relativos ao próprio clipe (o começo do clipe é `00:00:00`).
- Respeite `duracao_max_s` do formato ao estimar a duração total.
- Use apenas `clip_id`s presentes nos TRANSCRIPTS.
