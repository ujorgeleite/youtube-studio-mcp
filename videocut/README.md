# VideoCut

Montagem por conteúdo, 100% local. O VideoCut descobre as histórias que existem
nos seus takes, mostra as evidências de cada uma e gera uma primeira montagem
para continuar a edição no Filmora.

O resultado é uma montagem editorial forte e revisável, não um corte final. O
modelo pode errar intenção, humor e contexto familiar; por isso toda afirmação
aponta para arquivo e timestamp, e nada é montado sem a sua revisão.

## Instalação

Requisitos: macOS com Apple Silicon, Python 3.12+, `ffmpeg`/`ffprobe` no PATH.

```bash
cd videocut
make install
make doctor
make ui          # http://localhost:8090
```

Na primeira análise os modelos são baixados do Hugging Face e depois ficam em
cache: Whisper large-v3-turbo (~1,6 GB) e Qwen3-VL 8B 4-bit (~5,8 GB) ou 4B
(~3,1 GB). Escolha o modelo na tela Material ou em `config/modelos.yaml`.

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

Veja `CONTEXT.md` para arquitetura e `PLANO.md` para o histórico das fases.
