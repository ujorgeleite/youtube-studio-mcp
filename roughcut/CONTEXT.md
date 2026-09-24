# Contexto do Roughcut

## Propósito

`roughcut/` é uma ferramenta local para acelerar a pré edição de vídeos. Ela
analisa clipes raw, identifica fala e pausas, propõe cortes revisáveis e gera
MP4s para continuar a edição no Filmora. Também mantém o pipeline original de
pré montagem por formato editorial.

O foco é preparar material para edição humana. Nenhum vídeo raw é alterado.

## Limites do monorepo

- O MCP server na raiz é outro produto e não deve ser alterado por módulos do
  Roughcut.
- O Roughcut tem venv, dependências, `Makefile` e imports próprios.
- Módulos novos de vídeo vivem em `roughcut/`; podem compartilhar utilitários
  internos apenas quando o domínio e as dependências forem compatíveis.
- `ffmpeg` e `ffprobe` são pré requisitos do sistema, fora do `requirements.txt`.

## Produtos existentes

### 1. Pipeline de pré montagem

Entrada: pasta de clipes, formato YAML e transcrições. O pipeline produz um
stringout MP4 a partir de uma cut list.

| Passo | Código | Função |
|---|---|---|
| Transcrição | `steps/transcribe.py` | Whisper local, transcript timestampado |
| Ordenação | `steps/order.py` | LLM recebe formato e transcripts e retorna cut list |
| Montagem | `steps/assemble.py` | ffmpeg corta, concatena e cria slugs de B roll |

O prompt editorial fica isolado em `prompts/ordenacao.md`; os formatos ficam em
`formats/`. A ordenação por LLM é o único trecho não determinístico.

### 2. Corte inteligente por fala e frase

É a funcionalidade principal da interface NiceGUI atual.

1. Seleciona uma pasta raw e mostra miniaturas dos vídeos.
2. Analisa os clipes com Silero VAD e MLX Whisper `large-v3-turbo`.
3. Calcula cortes apenas entre palavras, usando regras de pausa, respiro,
   crossfade, proteção de pausas e retakes.
4. Permite revisar cada vídeo e ligar ou desligar cada corte antes do render.
5. Renderiza MP4s com ffmpeg, sem sobrescrever os originais.

Arquivos centrais:

| Área | Código |
|---|---|
| Interface e estado do lote | `ui/silence.py` |
| Player de prévia sem gravar arquivo | `ui/review_preview.py`, `ui/review_preview.js` |
| VAD e room tone | `smartcut/audio.py` |
| Whisper e glossário | `smartcut/transcript.py`, `config/glossario.yaml` |
| Regras e presets | `smartcut/cuts.py`, `smartcut/config.py`, `config/presets.yaml` |
| Orquestração e cache | `smartcut/pipeline.py`, `smartcut/cache.py` |
| Render | `smartcut/render.py`, `silence/render.py` |
| SRT, FCPXML e relatório de revisão | `smartcut/export.py` |

## Interface atual

### Análise e revisão

- Grade de vídeos com miniatura, seleção, etapa e porcentagem visual.
- Timeline, transcrição, cortes sugeridos e controles por vídeo analisado.
- Prévia do original e da versão com os cortes marcados, sem renderizar MP4.
- Estado por arquivo preservado ao trocar o vídeo em revisão.
- Erros de ffmpeg e vídeos sem áudio recebem mensagens curtas e não interrompem
  os outros arquivos do lote.

### Renderização do lote

Ao clicar em **Processar selecionados**:

- controles e prévia de análise ficam ocultos;
- aparece um painel central com cronômetro grande, progresso, itens finalizados
  e tempo de vídeo removido;
- a grade mostra somente os vídeos selecionados ainda pendentes ou renderizando;
- cada item concluído, ignorado ou com falha deixa a grade e vira uma linha de
  **Relatório em formação**;
- o painel e o relatório atualizam a cada segundo.

## Dados de saída

Para uma pasta `raw`, o corte inteligente cria uma pasta irmã:

```text
raw__corte-inteligente/
├── videos/       # processed_<origem>__sem-silencios.mp4
├── subtitles/    # fala cortada em SRT
├── timelines/    # FCPXML apontando ao original
├── reports/      # revisão por vídeo e resumo incremental do lote
├── plans/        # plano de cortes e room tone
├── .audio/       # temporários de extração e normalização
└── .cache/       # VAD e transcrição reutilizáveis
```

Durante análise/render, `smartcut/batch_report.py` regrava:

```text
reports/<lote>__summary.json
reports/<lote>__summary.md
```

Cada linha do resumo contém fonte, status, duração original/final, segundos
removidos, número de cortes, tempo de análise/render e caminhos dos artefatos.

## Como executar

```bash
cd roughcut
make install
make test
make silence-ui
```

Abra `http://localhost:8080` para a interface. Outros comandos estão em
`roughcut/Makefile`; `make help` lista todos.

## Testes e critérios de qualidade

- `make test` não baixa modelo Whisper nem chama LLM real.
- Há testes de ffmpeg para montagem, transcrição mockada, parsing do LLM mockado,
  VAD, regras de corte, exportação, saída organizada, interface e relatório de
  lote.
- A qualidade editorial da ordenação por LLM e da escolha de cortes deve ser
  validada com vídeos reais. Testes cobrem contrato, estado e comportamento
  determinístico, não julgamento criativo.

## Como criar um novo módulo de vídeo

1. Crie um pacote claro em `roughcut/`, com dependências locais já existentes
   ou novas dependências adicionadas somente a `roughcut/requirements.txt`.
2. Mantenha análise, plano de edição e render separados. O plano deve ser JSON
   serializável e permitir reprocessar sem rodar modelos de novo.
3. Coloque artefatos em subpastas da saída por tipo, como `videos/`, `reports/`
   e `plans/`; use prefixos para MP4s derivados.
4. Projete etapas demoradas para atualizarem o estado por arquivo. A UI deve
   sobreviver a falhas individuais e continuar o restante do lote.
5. Adicione testes determinísticos com fixtures pequenas; não baixe modelos nem
   processe mídia grande durante a suíte.
6. Se a funcionalidade exigir revisão, preserve as escolhas por arquivo antes
   de iniciar o render.

## Próximas evoluções

O backlog em `BACKLOG.md` concentra melhorias de resumo e métricas. Antes de
criar um novo módulo, registre ali o fluxo de entrada, plano, saída e o que deve
aparecer em tempo real para quem está editando.
