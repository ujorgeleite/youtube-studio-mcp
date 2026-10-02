# Capacidades do backend Roughcut

Este arquivo é o catálogo técnico para agentes e pessoas que forem estender o
Roughcut. Ele descreve apenas comportamento verificado no código. **Não trate
interfaces marcadas como contrato/protótipo como pipeline operacional.**

## Invariantes globais

- Vídeos em `raw` são sempre entradas: não podem ser movidos, apagados ou
  sobrescritos.
- Derivados do Corte Inteligente ficam em uma pasta irmã,
  `<raw>__corte-inteligente/`; cache, áudio temporário, relatórios e MP4s vivem
  abaixo dela.
- Análise, plano de cortes e render são etapas separadas. O plano é a fonte de
  verdade revisável; renderizar não deve recomputar VAD, Whisper ou cortes.
- Lotes congelam os caminhos selecionados no início. A seleção visível é limpa
  para que o lote seguinte seja uma escolha nova.
- Uma falha em um arquivo não encerra o restante do lote. Vídeos sem áudio e
  B-roll são estados terminais distintos de falha.

## Corte Inteligente operacional

| Capacidade | Módulo/API | Estado e contrato |
|---|---|---|
| Descobrir vídeos | `silence.analyze.list_videos` | Lista arquivos de vídeo de primeiro nível: MP4, MOV, MKV, M4V, WebM e AVI; ordenação por nome. |
| Sondar mídia | `probe_duration`, `probe_media` | `ffprobe` retorna duração; `probe_media` também informa presença de áudio. |
| Proxy DJI para análise | `resolve_analysis_source` | Usa `.LRF` somente se tiver áudio e duração compatível; o render usa sempre o original. |
| Miniaturas | `extract_thumbnail` | Gera JPEG 320×180 em cache, em um frame representativo; nunca escreve no raw. A UI as carrega progressivamente em `<saída>/.cache/thumbnails/`. |
| Áudio | `smartcut.preprocess.has_audio_stream`, `extract_audio`, `normalize_loudness` | Detecta stream, extrai mono 48 kHz e pode normalizar para LUFS configurado. |
| VAD e room tone | `smartcut.audio.speech_regions`, `room_tone_region` | Silero VAD identifica regiões de fala e uma região segura de ambiente. |
| Transcrição | `smartcut.transcript.transcribe_words` | MLX Whisper produz palavras com timestamps e aplica glossário configurável. |
| Cache | `smartcut.cache.StageCache` | Cache por arquivo para VAD e transcrição dentro de `.cache/`; regras podem ser recalculadas sem reinferência. |
| Plano de cortes | `smartcut.pipeline.analyze_clip` | Produz `CutPlan` com palavras, cortes, pausas protegidas e retakes; exporta plano, SRT, Markdown, FCPXML e room tone. |
| Regras | `smartcut.config`, `smartcut.cuts` | Presets YAML; pausa dentro/após frase, trecho mínimo, respiro, crossfade, proteção dramática e punch-in. Nem toda opção de UI altera o MP4 atual — veja limites. |
| Retakes | `smartcut.retakes.detect_retakes` | Detecta repetição por sentenças; o plano pode propor remoção reversível. |
| Revisão | `ui.review_preview`, `ui/silence.py` | Player do original com saltos locais nos cortes, timeline, transcrição, visualização e restauração individual de cortes. |
| Render | `smartcut.render.render_with_handles` → `silence.render.render_plan` | Mantém intervalos aprovados, gera MP4 em `videos/`, acompanha timeline do ffmpeg por callback e salva plano de render. Usa encoder acelerado disponível ou `libx264`. |
| Render paralelo | `ui/silence.py` | Semáforo de 1–3 workers somente para render. Cada item recebe fração real baseada em tempo codificado pelo ffmpeg. |
| Temperatura | `smartcut.thermal.ThermalGovernor` | Lê estado térmico macOS e `macmon` se presente; pausa cooperativamente em estado sério ou ≥95 °C e retoma em condição segura. |
| Resumo do lote | `smartcut.batch_report` | Atualiza JSON e Markdown em `reports/` durante análise/render, com status, duração, cortes, tempos e artefatos. |

### Estados operacionais por vídeo

Na interface, os estados relevantes são: `Pronto para analisar`, `Na fila`,
`Extraindo áudio`, `Normalizando áudio`, `Detectando fala e transcrevendo`,
`Cortes prontos`, `Sem áudio — ignorado`, `Sem diálogo — B-roll`, `Na fila para
renderização`, `Renderizando`, `Concluído`, `Falhou` e `Interrompido — retomar`.

Para uma extensão, preserve estados terminais e atualize o progresso de maneira
monótona. Uma UI não deve exibir relógio/temperatura quando não houver lote
ativo.

### Saídas do Corte Inteligente

```text
<raw>__corte-inteligente/
├── videos/       MP4s processados
├── subtitles/    SRT pós-corte
├── timelines/    FCPXML apontando para o original
├── reports/      revisão por vídeo e resumo incremental JSON/Markdown
├── plans/        CutPlan e região de room tone
├── .audio/       áudio extraído/normalizado
└── .cache/       VAD, transcrição e miniaturas reutilizáveis
```

## Pipeline de pré-montagem editorial

Este é um produto paralelo ao Corte Inteligente, mas compartilha ffmpeg e a
política de não alterar originais.

| Etapa | Módulo | Capacidade |
|---|---|---|
| Inventário e transcrição | `steps.transcribe` | Enumera clipes, executa Faster Whisper local e formata transcripts por `clip_id`. |
| Formato e prompt | `steps.order` | Lê YAML editorial e prompt Markdown, cria solicitação para LLM, tolera JSON em cercas e valida a presença de `roughcut`. |
| Ordenação | `steps.order.order` | Chama Anthropic por padrão, mas aceita função injetada para teste ou outro provedor. É a única etapa não determinística. |
| Montagem | `steps.assemble` | Corta, normaliza, concatena, cria slugs de B-roll e MP4 stringout com ffmpeg. |
| Frames editoriais | `steps.frames` | Extrai thumbnails em grade, primeiro frame por clipe e frames dos takes selecionados para `cold_open`. |
| Registro reprodutível | `steps.run_record.RunRecord` | Cria bundle de run com manifesto, eventos JSONL, ambiente, parâmetros, artefatos, prompt, resposta e saída. |
| Orquestração | `run.py` | Oferece execução completa, dry-run de assemble, fase manual de prompt/resposta e persistência de artefatos. |

## Interfaces e entradas

- `make silence-ui` ou `python ui/app.py`: interface NiceGUI operacional do
  Corte Inteligente, porta 8080.
- `make smartcut INPUT=<pasta> FORMAT=<preset>`: análise por fala/frase pela
  CLI; produz os artefatos do plano.
- `make run INPUT=<pasta> FORMAT=<yaml> OUTPUT=<mp4>`: pré-montagem completa.
- `make dry-run`: monta a fixture ou uma cut-list já existente sem Whisper/LLM.
- `corte_inteligente/app.py --mock`: wireframe/máquina de estados de demonstração.
  Sem `--mock`, essa entrada encaminha para a UI operacional; não é um segundo
  backend de produção.

## Contratos e protótipos não operacionais

`corte_inteligente/backend/` existe para desacoplar o wireframe da futura
integração. Hoje:

- `mock.py` e `engine.py` são funcionais apenas para simular seleção, lote,
  paralelismo, interrupção e temperatura determinística.
- `preview.py` é funcional: cria poster JPEG 320 px e trecho H.264 480p de
  45 segundos sob demanda em cache; a UI oficial usa seu próprio fluxo de
  miniaturas progressivas e ainda não chama esse adaptador de proxy.
- `probe.py`, `analyze.py`, `plan.py`, `render.py` e `thermal.py` são **stubs**
  com `NotImplementedError` ou resposta indisponível. Não os chame em produção
  até conectá-los às APIs `silence.*` e `smartcut.*` acima.

## Limites conhecidos para implementações futuras

- O crossfade de áudio e o disfarce de jump cut são mantidos no plano/regra,
  mas o render atual concatena áudio sem crossfade e não aplica disfarce visual.
- Pausas dramáticas podem ser protegidas quando fornecidas ao plano; ainda não
  há classificação automática completa desse tipo de pausa.
- A prévia revisa o original no navegador e pula cortes localmente. Proxy de
  avaliação sob demanda está disponível como adaptador, mas não ligado ao
  player oficial.
- A thread/UI deve pausar geração opcional de previews enquanto análise ou
  render estiverem ativos; essas tarefas não podem competir com ffmpeg, VAD ou
  Whisper.

## Como estender com segurança

1. Reaproveite `analyze_clip` e `render_with_handles` quando a intenção for
   evoluir o Corte Inteligente. Não replique VAD, cache ou render em um novo
   módulo.
2. Adicione estado e artefato por arquivo antes de adicionar um novo painel de
   UI. Atualize `batch_report` se o novo estado fizer parte de lote.
3. Mantenha entradas de modelos/LLM lazy e injetáveis em testes; testes não
   podem baixar modelos, chamar rede ou processar mídia longa.
4. Para uma mudança de render, preserve o `CutPlan`, a revisão individual e o
   callback de progresso em tempo real.
5. Documente na tabela acima qualquer capacidade nova, incluindo se está
   operacional, experimental ou apenas contrato.
