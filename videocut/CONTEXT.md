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

1. **Fatos antes de interpretação.** Transcrição e observação visual são fatos
   com timestamp. Propostas só citam fatos via `Evidence`; o validador rejeita
   citações que não existem no inventário.
2. **Falta material é uma resposta válida.** O planejador pode concluir que não
   há história completa e sugerir o que gravar.
3. **Imagem e áudio são faixas separadas.** A fala de um take pode continuar
   enquanto aparecem imagens de outro.
4. **Tudo em cache.** Pedir uma versão mais curta recalcula só a proposta.
5. **Um modelo pesado por vez.** Whisper e o modelo visual não ficam carregados
   juntos.

## Estrutura

| Pacote | Responsabilidade |
|---|---|
| `core/` | Schemas, serialização, projeto persistido, cache, formatação de tempo |
| `media/` | ffprobe, miniaturas, frames, mudanças de cena, áudio e proxies |
| `analysis/` | Whisper, modelo visual, inventário de momentos |
| `story/` | Planejador editorial, critérios de suficiência, validador determinístico |
| `montage/` | Plano de montagem, render ffmpeg, legendas, timeline, pacote de entrega |
| `ui/` | Interface NiceGUI em cinco etapas |

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
gerada com `ffmpeg -f lavfi`. Qualidade editorial é validada com material real
(fase 11), não pela suíte.
