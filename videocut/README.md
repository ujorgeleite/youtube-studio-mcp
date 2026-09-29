# VideoCut

Montagem por conteúdo, 100% local. O VideoCut descobre as histórias que existem
nos seus takes, mostra as evidências de cada uma e gera uma primeira montagem
para continuar a edição no Filmora.

**Seus originais estão seguros:** o VideoCut nunca apaga, move ou sobrescreve
nada na pasta de origem e recusa uma pasta de saída dentro dela. Tudo o que ele
gera vai para a pasta irmã `raw__videocut/`.

O resultado é uma montagem editorial forte e revisável, não um corte final. O
modelo pode errar intenção, humor e contexto familiar; por isso toda afirmação
aponta para arquivo e timestamp, e nada é montado sem a sua revisão.

## Instalação

Requisitos: macOS com Apple Silicon, Python 3.12+, `ffmpeg`/`ffprobe` no PATH.

```bash
cd videocut
make install
make models      # baixa uma vez: Whisper (~1,6 GB) + Qwen3-VL 8B (~5,8 GB)
make doctor      # confirma que tudo está local
make ui          # http://localhost:8090
```

### Funciona sem internet

Depois do `make models`, o VideoCut roda 100% offline: a interface e a CLI
iniciam com `HF_HUB_OFFLINE=1` e carregam os modelos só do disco
(`~/.cache/huggingface/hub`). A única etapa que acessa a rede é o próprio
`make models` (ou a primeira análise, se algum modelo ainda faltar). Para
baixar também o 4B: `make models MODELS=qwen3-vl-8b,qwen3-vl-4b`.

O download é protegido contra travamentos: se ficar 90 s sem receber dados, é
reiniciado de onde parou (até 5 tentativas) e o progresso aparece na tela.

## Fluxo

1. **Material** — escolha a pasta raw, selecione os takes e, se quiser, diga o
   que queria contar, o formato e a duração desejada.
2. **Análise** — Whisper transcreve as falas; o modelo visual descreve os takes
   em duas passagens (ampla + detalhe onde vale a pena). Um take com falha não
   interrompe o lote.
3. **Histórias** — propostas de um ou vários vídeos, ou “falta material”, com
   critérios (mensagem, abertura, desenvolvimento, encerramento, cobertura
   visual, independência) e evidências clicáveis.
4. **Revisão** — prévia da sequência com B-roll sobre a fala, sem render.
   Exclua, restaure, mova, proteja blocos, ajuste frases, troque trechos e peça
   uma versão mais curta sem analisar de novo.
5. **Entrega** — MP4, plano JSON, relatório editorial, SRT e timeline XML por
   vídeo, em `raw__videocut/entregas/`.

### Proxies da câmera (.LRF)

Arquivos `.LRF` com o mesmo nome do vídeo (ex.: `DJI_0001.MP4` +
`DJI_0001.LRF`) são detectados automaticamente e usados para miniaturas,
análise e prévia, o que acelera tudo. O render final sempre lê o original.

### Filmora

A timeline é gerada em Final Cut Pro 7 XML (o formato que o Filmora exporta):
V1 com os blocos, V2 com imagens de apoio, A1 com fala/ambiente e A2 com o som
do B-roll. Importe em **Arquivo → Importar mídia → Importar Timeline XML**. A
compatibilidade depende da versão do Filmora e ainda precisa ser confirmada; o
MP4 é a entrega de referência.

## Linha de comando

```bash
make analyze INPUT=/caminho/raw                          # análise sem interface
make compare INPUT=/caminho/raw EDIT=/caminho/final.mp4  # proposta × sua edição
make benchmark INPUT=/caminho/raw MODELS=qwen3-vl-4b,qwen3-vl-8b
```

`compare` transcreve a sua edição final, alinha as falas com os takes e mede
recall, precisão e concordância de ordem. `benchmark` mede tempo, memória de
pico e respostas inválidas de cada modelo, com descrições lado a lado.

## Ajustes editoriais

- `config/canal.yaml` — regras do canal e formatos; pesam mais que o modelo.
- `prompts/historias.md` — o pedido ao planejador editorial.
- `prompts/visao_ampla.md`, `prompts/visao_detalhe.md` — descrição visual.
- `config/glossario.yaml` — nomes e lugares para o Whisper.

Mudar um prompt invalida só o cache da etapa afetada.

Veja `ARCHITECTURE.md` para os diagramas de arquitetura e fluxo, `CONTEXT.md` para limites
e decisões, e `PLANO.md` para o histórico das fases.
