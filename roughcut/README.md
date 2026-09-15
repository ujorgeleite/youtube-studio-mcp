# roughcut

Pipeline de **pré-montagem** de vídeo. Recebe uma pasta de clipes brutos e um
formato, e cospe um **stringout** (MP4 pré-montado) mais uma crítica da ordenação.

> **Projeto isolado.** Vive num monorepo ao lado de um MCP server, mas não
> compartilha venv, dependências nem imports com ele. A única coisa em comum é o
> `.git` da raiz. Nada aqui importa código do MCP.

## Os 3 passos

| Passo | Módulo | Determinístico? | Testado? |
|------|--------|-----------------|----------|
| 1. transcribe | `steps/transcribe.py` | sim (Whisper local) | só a formatação (Whisper mockado) |
| 2. order | `steps/order.py` | **não** (LLM) | só o parsing (LLM mockado) |
| 3. assemble | `steps/assemble.py` | sim (ffmpeg) | sim, ponta a ponta com fixtures |

A **qualidade** da ordenação (passo 2) NÃO é coberta por teste — é o passo do LLM,
não-determinístico. Você valida rodando de verdade num vídeo.

## Pré-requisitos

- **ffmpeg** instalado no sistema (não é pacote pip):

  ```bash
  ffmpeg -version   # confirme que está instalado
  brew install ffmpeg   # macOS, se faltar
  ```

- Python 3.10+ e um venv **próprio desta pasta**.

## Setup

```bash
cd roughcut
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Para o passo 2 (LLM), configure as credenciais da Anthropic (`ANTHROPIC_API_KEY`
ou `ant auth login`).

## Uso

```bash
# pipeline completo
.venv/bin/python run.py --input ./clipes_brutos --format qualidade-de-vida --output ./stringout.mp4

# só reprocessar o assemble a partir de um cut-list já salvo (pula Whisper e LLM)
.venv/bin/python run.py --dry-run --cut-list ./stringout.cut-list.json --input ./clipes_brutos --output ./stringout.mp4

# demonstração autocontida (usa a cut-list e clipes de fixture)
.venv/bin/python run.py --dry-run
```

Flags: `--input`, `--format`, `--output`, `--dry-run`, `--cut-list`, `--model-size`.

## O cut-list (schema)

O passo 2 produz e o passo 3 consome:

```json
{
  "roughcut": [
    { "beat": "cold_open", "clips": [ {"clip_id": "C01", "in": "00:00:03", "out": "00:00:08"} ], "broll_suggestion": "" },
    { "beat": "broll_slot", "clips": [], "broll_suggestion": "drone sobre a cidade" }
  ]
}
```

Beats com `clips: []` viram um slug de 1s (preto com o texto da sugestão) no
stringout, marcando onde entra cada B-roll.

## O "cérebro" (prompts/ordenacao.md)

`prompts/ordenacao.md` é o **cérebro** do passo 2 e é onde se itera a qualidade —
mude o texto sem tocar no código. Hoje é um placeholder funcional; substitua pelo
prompt real de ordenação quando for validar de verdade.

## Testes

```bash
cd roughcut
.venv/bin/python -m pytest -q
```

Os testes **não** baixam modelo de Whisper nem chamam LLM real. Os clipes de
fixture são cores sólidas geradas na hora via ffmpeg (não são commitados).
