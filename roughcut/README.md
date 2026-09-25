# Roughcut

Ferramenta local para preparar vídeos antes da edição. O fluxo principal é o
**removedor inteligente de silêncios**: analisa fala, propõe cortes revisáveis e
gera cópias MP4 prontas para importar no editor.

> **Projeto isolado.** Vive num monorepo ao lado de um MCP server, mas não
> compartilha venv, dependências nem imports com ele. A única coisa em comum é o
> `.git` da raiz. Nada aqui importa código do MCP.

## Rodar o removedor de silêncios

Este é o roteiro para uma pessoa nova testar a interface.

### 1. Pré-requisitos

- **macOS com Apple Silicon (M1, M2, M3 ou M4)**. A análise de fala usa
  `mlx-whisper` e foi validada nesse ambiente.
- **Python 3.10 ou superior**. Confirme com `python3 --version`.
- **ffmpeg e ffprobe** instalados no sistema. No macOS com Homebrew:

  ```bash
  brew install ffmpeg
  ffmpeg -version
  ffprobe -version
  ```

- Internet na primeira análise: o modelo local de Whisper é baixado uma vez e
  fica em cache. Reserve espaço livre em disco para ele e para os MP4s gerados.

### 2. Instalação

Abra o Terminal na raiz do repositório e execute:

```bash
cd roughcut
make install
make doctor
```

`make install` cria `roughcut/.venv` e instala somente as dependências deste
projeto. `make doctor` confirma `ffmpeg`, `ffprobe` e os imports de Python antes
de abrir a interface.

### 3. Abrir a interface

```bash
cd roughcut
make silence-ui
```

Mantenha esse terminal aberto e acesse [http://localhost:8080](http://localhost:8080).

### 4. Processar um lote

1. Clique em **Escolher pasta** e selecione a pasta `raw` com os vídeos.
2. Clique em **Carregar vídeos**. As miniaturas confirmam os arquivos lidos.
3. Marque somente os vídeos desejados e clique em **Analisar selecionados**.
   A primeira execução pode levar mais tempo por baixar o modelo.
4. Selecione cada vídeo no campo **Vídeo analisado**, revise a timeline e use
   **Remover** ou **Restaurar** em cada corte proposto.
5. Escolha **2 em paralelo** para o uso normal. Tente **3 em paralelo** se o
   Mac tiver folga; volte para 2 se ele ficar pesado.
6. Clique em **Processar selecionados**. A tela troca para execução do lote,
   com cronômetro, progresso e relatório por vídeo.

### 5. Encontrar os resultados

Nada sobrescreve a pasta raw. Para uma origem chamada `raw`, a ferramenta cria
uma pasta irmã chamada `raw__corte-inteligente/`:

```text
raw__corte-inteligente/
├── videos/       # MP4s: processed_<origem>__sem-silencios.mp4
├── reports/      # resumo do lote e revisão em Markdown
├── subtitles/    # SRT da fala mantida
├── timelines/    # FCPXML apontando ao vídeo original
├── plans/        # JSON dos cortes
├── .audio/       # temporários
└── .cache/       # VAD e transcrição reutilizáveis
```

O painel **Relatório em formação** mostra, para cada vídeo, cortes aplicados,
duração removida, duração antes/depois, tempo de render e eventuais erros.

### Solução rápida de problemas

| Situação | Ação |
|---|---|
| `ffmpeg não encontrado` | Rode `brew install ffmpeg`, feche e reabra o Terminal, depois execute `make doctor`. |
| A página não abre | Confirme que `make silence-ui` continua rodando e abra `http://localhost:8080`. |
| Vídeo marcado como sem áudio | O arquivo não possui uma trilha de áudio utilizável; ele é ignorado e os demais continuam. |
| A análise demora no primeiro vídeo | Aguarde o download e carregamento inicial do modelo Whisper. As próximas análises reutilizam o cache. |
| O Mac fica pesado | Altere **Renderização** de 3 para 2 ou 1 por vez antes de processar. |

## Outros fluxos do projeto

Além do removedor, o projeto mantém o pipeline de **pré-montagem**: recebe
clipes e um formato editorial, e produz um stringout MP4 com uma crítica de
ordenação.

### Os 3 passos

| Passo | Módulo | Determinístico? | Testado? |
|------|--------|-----------------|----------|
| 1. transcribe | `steps/transcribe.py` | sim (Whisper local) | só a formatação (Whisper mockado) |
| 2. order | `steps/order.py` | **não** (LLM) | só o parsing (LLM mockado) |
| 3. assemble | `steps/assemble.py` | sim (ffmpeg) | sim, ponta a ponta com fixtures |

A **qualidade** da ordenação (passo 2) NÃO é coberta por teste — é o passo do LLM,
não-determinístico. Você valida rodando de verdade num vídeo.

### Executar a pré-montagem

Para o passo de ordenação por LLM, configure `ANTHROPIC_API_KEY` ou execute
`ant auth login` antes de rodar o pipeline.

```bash
# pipeline completo
.venv/bin/python run.py --input ./clipes_brutos --format qualidade-de-vida --output ./stringout.mp4

# só reprocessar o assemble a partir de um cut-list já salvo (pula Whisper e LLM)
.venv/bin/python run.py --dry-run --cut-list ./stringout.cut-list.json --input ./clipes_brutos --output ./stringout.mp4

# demonstração autocontida (usa a cut-list e clipes de fixture)
.venv/bin/python run.py --dry-run
```

Flags: `--input`, `--format`, `--output`, `--dry-run`, `--cut-list`, `--model-size`.

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
