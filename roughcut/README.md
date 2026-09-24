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

## Interface de revisão

A ferramenta de remoção inteligente usa apenas NiceGUI. Ela abre uma tela de
revisão com regras à esquerda, timeline e cortes ao centro, e resultado à direita.

```bash
make silence-ui
```

## Remover silêncios

Ela recebe uma pasta com vídeos raw, usa Silero VAD e MLX Whisper para gerar
cortes entre palavras e mostra os cortes propostos para revisão antes do render.

```bash
make silence-ui
# depois abra http://localhost:8080
```

Existem três políticas por vídeo:

- **Limpar ao redor dos diálogos:** detecta vários blocos de diálogo no mesmo
  arquivo, remove os espaços antes, depois e entre blocos, e preserva pausas
  naturais dentro de cada bloco.
- **Remover todos os silêncios:** mantém cada ilha de fala com pequenas margens.
- **Remoção cautelosa:** preserva pausas curtas e reduz pausas longas para uma
  duração mínima, evitando cortes secos no meio da fala.

O processamento nunca altera os arquivos raw. Por padrão, cria uma pasta irmã:

```text
<nome-da-pasta-raw>__remocao-de-silencios_<data>/
├── video__sem-silencios.mp4
└── video__plano-silencios.json
```

O JSON registra os silêncios encontrados, blocos de diálogo, parâmetros e
intervalos mantidos. A análise e o corte usam `ffmpeg`/`ffprobe`; não chamam LLM.

A tela usa uma lista compacta com filtros, indicadores de ganho e um painel de
inspeção do vídeo selecionado. A análise e a renderização podem rodar em
paralelo, com limite configurável. Quando houver um proxy DJI `.LRF` com áudio e
duração compatível, ele é usado para análise, waveform e miniatura; o render
final sempre usa o `.MP4` original.

Quando a remoção total não atingir os limites definidos na tela, o vídeo é
copiado para a pasta de resultado sem reencodificação. Marque **Sempre
renderizar** para ignorar essa decisão.

## Corte inteligente por fala/frase

O novo fluxo usa Silero VAD para mapear fala, `mlx-whisper` com
`large-v3-turbo` e timestamps por palavra, e regras que só cortam entre
palavras. Ele mantém respiro, preserva pausas configuradas e detecta retakes
consecutivos, mantendo o último take.

```bash
make smartcut INPUT=/caminho/para/raw FORMAT=colab
```

Os presets ficam em `config/presets.yaml`; o glossário de nomes e expressões
fica em `config/glossario.yaml`. A pasta irmã `raw__corte-inteligente/` organiza
os resultados por tipo:

```text
raw__corte-inteligente/
├── videos/     # processed_<video>__sem-silencios.mp4
├── subtitles/  # SRT
├── timelines/  # FCPXML apontando ao original
├── reports/    # revisão em Markdown
├── plans/      # JSON da análise, room tone e plano de render
├── .audio/     # temporários de normalização
└── .cache/     # VAD e transcrição para reprocessar sem usar modelos de novo
```

Vídeos sem trilha de áudio aparecem como **Sem áudio — ignorado** na fila. Eles
não interrompem os outros arquivos, pois não há fala ou silêncio para analisar.

DeepFilterNet permanece opcional: a distribuição atual precisa de Rust/Cargo
para compilar no Python 3.14. A normalização `loudnorm` em duas passadas já está
disponível na interface.

## Runs (logs ricos para IA)

Cada execução do pipeline legado escreve um bundle autocontido em `runs/<stamp>__<slug>/`:
`run.json` (manifesto: params, ambiente, timing por passo, artefatos, status),
`events.jsonl` (log estruturado append-only) e os artefatos de cada passo
(`transcripts.txt`, `prompt.md`, `llm_response.txt`, `cut-list.json`, `critica.json`).
A pasta `runs/` é local e fica no `.gitignore`.

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
