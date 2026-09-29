# Contexto do VideoCut

## Propósito

`videocut/` monta vídeos por conteúdo. Analisa localmente o que é dito e o que
aparece nos takes, propõe uma ou várias histórias com evidências, deixa a pessoa
revisar a sequência e gera um pacote para terminar a edição no Filmora.

O resultado é uma primeira montagem editorial revisável, não um corte final.
Nenhum vídeo original é alterado.

## Limites do monorepo

- Projeto irmão do MCP (raiz) e do `roughcut/`. Não importa código de nenhum
  dos dois, nem é importado por eles. Integração só por arquivos.
- Tem `.venv`, `requirements.txt`, `Makefile` e testes próprios. Rode tudo a
  partir de `videocut/`.
- `ffmpeg` e `ffprobe` são pré-requisitos do sistema.
- Conceitos reaproveitados do Roughcut (cache por etapa, plano JSON, revisão
  por arquivo, progresso ao vivo) foram reescritos aqui.

## Princípios

0. **A pasta de origem é intocável.** O VideoCut nunca apaga, move, renomeia
   ou sobrescreve nada nela, nem grava arquivos novos lá dentro. Toda escrita
   passa por `core/safety.py::ensure_writable`: `Project.open` protege a pasta
   e recusa uma saída dentro dela, e `run_ffmpeg`, `write_json`, `write_text` e
   cada `Path.replace` conferem o destino antes de gravar. Links simbólicos são
   resolvidos. Não existe código de remoção no projeto; qualquer limpeza futura
   deve se limitar a `raw__videocut/.work` e `.cache` e também passar pela proteção.
1. **Fatos antes de interpretação.** Transcrição e observação visual são fatos
   com timestamp. Propostas só citam fatos via `Evidence`; o validador rejeita
   citações que não existem no inventário.
2. **Falta material é uma resposta válida.** O planejador pode concluir que não
   há história completa e sugerir o que gravar.
3. **Imagem e áudio são faixas separadas.** A fala de um take pode continuar
   enquanto aparecem imagens de outro.
4. **Tudo em cache.** Pedir uma versão mais curta recalcula só a proposta.
5. **Offline por padrão.** `core/offline.py` liga `HF_HUB_OFFLINE` antes de
   qualquer import de modelo; só `analysis/models.py` baixa, num subprocesso
   com rede, sem xet, com vigia de travamento e retomada.
6. **Um modelo pesado por vez.** Whisper e o modelo visual não ficam carregados
   juntos.
7. **Cargas longas cuidam do Mac.** `core/thermal.py` pausa acima do limite
   (opcional por projeto); `core/keepawake.py` impede o sono durante o trabalho;
   `core/power.py` só lê ajustes de energia — o app nunca altera o macOS.

## Estrutura

Diagramas de pacotes, domínio, fluxo da UI, pipeline e invariantes: `ARCHITECTURE.md`.

| Pacote | Responsabilidade |
|---|---|
| `core/` | Schemas, serialização, projeto persistido, cache, formatação de tempo |
| `media/` | ffprobe, miniaturas, frames, mudanças de cena, áudio e proxies |
| `analysis/` | Whisper, modelo visual, inventário de momentos |
| `story/` | Planejador editorial, critérios de suficiência, validador determinístico |
| `montage/` | Plano de montagem, render ffmpeg, legendas, timeline, pacote de entrega |
| `ui/` | Interface NiceGUI em cinco etapas (`make ui`, porta 8090) |
| `proof/` | Comparação com edição real e benchmark de modelos |
| `cli.py` | `doctor`, `analyze`, `compare`, `benchmark` |

## Decisões de implementação

- O planejador cita **ids de momentos** (`T05.03`), não timestamps livres. O
  validador (`story/validate.py`) descarta ids inexistentes, prende tempos ao
  momento, expande cortes de fala para frases inteiras e troca citações que não
  existem pela transcrição real. Critérios estruturais (`story/criteria.py`)
  nunca podem ser “melhorados” pelo modelo: vale o status mais severo.
- A resposta bruta do planejador fica em cache; melhorar o validador não exige
  rodar o modelo de novo.
- Render por segmento: cada bloco vira um MP4 normalizado (leitura com `-ss/-t`
  na entrada) e os segmentos são concatenados sem recodificar. A chave de cache
  usa só posições relativas ao bloco: reordenar reaproveita tudo.
- Proxies `.LRF` da câmera entram em `Take.proxy`; `Take.analysis_path` é usado
  para miniatura, cenas, frames, áudio da transcrição e prévia.
- Callbacks da UI que continuam depois de um `await` usam `shell.notify` e
  `shell.go`, que operam no contêiner raiz (o botão original pode ter sido
  recriado).

## Saída

Para uma pasta `raw/`, a saída padrão é a pasta irmã `raw__videocut/`:

```text
raw__videocut/
├── project.json      # estado: seleção, intenção, análise, propostas, revisão
├── analise/          # inventário e histórias propostas
├── entregas/
│   └── proposta-a__v1/
│       ├── videos/  plans/  reports/  subtitles/  timelines/
├── .cache/           # transcrição e visão por arquivo, modelo e prompt
└── .work/            # miniaturas, frames, áudio e proxies temporários
```

## Testes

`make test` não baixa modelos nem executa inferência real. Mídia de teste é
gerada com `ffmpeg -f lavfi`; a UI é exercitada montando as páginas NiceGUI em
memória. Qualidade editorial é validada com material real (`make compare` e
`make benchmark`), não pela suíte.
