# Backlog do VideoCut

Quando a pessoa pedir “implementa o backlog”, siga os itens abertos na ordem,
marque `[x]` ao concluir (com `make test` verde e commit) e registre em `PLANO.md`.

- [x] **1. Desmarcar takes curtos demais** — `5b69f2e`
- [x] **2. Modo de cargas longas (proteção térmica)** — `18fe739` (`macmon` instalado)
- [x] **3. Manter o Mac acordado durante o trabalho** — `18fe739`
- [x] **4. Seletor “Rodar de madrugada” (sem senha)** — `16cdd85`
- [ ] **5. Acelerar a visão sem perder qualidade** — só depois do A/B no Episódio06
- [ ] **6. Área de Configurações com os prompts editáveis**
- [ ] **7. Skills e agentes configuráveis na área de Configurações** — depende do item 6

## Contexto


A análise real do Episódio06 (28 takes 4K HEVC, ~40 min no Qwen3-VL 8B, MacBook Air
M5 sem ventoinha) mostrou três necessidades:

1. Takes de poucos segundos custam ~50 s cada e raramente importam.
2. Cargas longas aquecem o Air; a aplicação deve **ler a temperatura, pausar
   acima de um limite saudável e só continuar quando esfriar**.
3. A pessoa quer deixar análises rodando de madrugada sem que o Mac durma.

Fatos verificados (leitura): `NSProcessInfo.thermalState` funciona sem sudo via
`osascript -l JavaScript` (retornou 1 = razoável durante a análise);
`pmset -g` na tomada mostra **`sleep 1`** (dorme após 1 min ocioso — hoje só não
dorme por asserções de outros processos); `lowpowermode 0`; `disksleep 10`;
`macmon` (brew, sem sudo, Apple Silicon) não instalado.

---

## Item 1 · Desmarcar takes curtos demais

- `config/modelos.yaml`: nova seção `material: {min_take_s: 5}`.
- `ui/material.py::open_folder`: ao carregar, **takes novos** abaixo do mínimo
  entram desmarcados (escolhas já salvas do usuário são respeitadas).
- Grade: selo `curto · 3 s` nesses takes; botão **“Desmarcar curtos (< 5 s)”**
  ao lado de Todos/Limpar; resumo mostra quantos foram desmarcados e o tempo
  estimado economizado.
- `cli.py analyze --min-take-s` com o mesmo padrão.
- Testes: `tests/test_ui.py` (seleção inicial, botão, respeito a escolhas salvas).

## Item 2 · Modo de cargas longas (proteção térmica)

**Significado:** análises/renders longos rodam de forma contínua no GPU; no Air
isso esquenta até o macOS reduzir o clock. O modo pausa o trabalho entre
chamadas quando o Mac passa do limite e retoma depois de esfriar, com
histerese para não ficar liga/desliga.

- Novo `core/thermal.py`:
  - `thermal_state()` → 0–3 via `osascript -l JavaScript` (sem dependências).
  - `temperature_c()` → °C de CPU/GPU via `macmon pipe -s 1` (JSON) se
    instalado; `None` caso contrário (formato do JSON verificado na implementação).
  - `ThermalGovernor(config, reader, sleep, cancel)`: `wait_if_hot()` pausa quando
    estado ≥ `pause_state` **ou** °C ≥ `pause_temp_c`; retoma quando estado ≤
    `resume_state` **e** °C ≤ `resume_temp_c`; consulta a cada `poll_s`;
    respeita cancelamento; acumula tempo pausado; `max_wait_min` evita espera
    infinita (continua com aviso).
- **Decisões da pessoa:** instalar `macmon` (vira pré-requisito como o ffmpeg:
  `brew install macmon`, feito na implementação com permissão) e o modo fica
  **opcional por projeto, desligado por padrão**.
- `config/execucao.yaml` (novo): `long_run: {pause_state: 2,
  resume_state: 1, pause_temp_c: 95, resume_temp_c: 80, poll_s: 10, max_wait_min: 45}`.
- Integração sem espalhar lógica:
  - `analysis/vlm.py`: `ThermalGuardedModel(inner, governor)` chama
    `wait_if_hot()` antes de cada `generate` (mesmo padrão do `CountingModel`
    em `proof/benchmark.py`) — cobre visão e planejador sem tocar `vision.py`.
  - `analysis/pipeline.py`: `wait_if_hot()` entre takes na transcrição;
    `AnalysisMonitor` ganha `thermal` (estado, °C, pausado desde, total pausado).
  - `montage/render.py::render_plan`: gancho `before_segment` chamado antes de
    cada bloco; `ui/delivery_view.py` passa o governador.
- UI:
  - Material: interruptor **“Modo de cargas longas”** (campo `long_run` em
    `core/project.py::Project`, padrão desligado; `cli.py analyze --long-run`).
    Com ele desligado, a temperatura continua visível, mas não pausa.
  - Análise e Entrega: selo ao vivo `🌡 78 °C · normal`; em pausa, painel âmbar
    “Esfriando o Mac · 96 °C → retoma em ≤ 80 °C · pausado há 02:10”, entrada
    no log e total de pausas no resumo final.
  - Cartão de atividade (`ui/activity.py`) mostra a pausa quando ocorrer em
    prévias longas.
- `make doctor`: mostra estado térmico e °C; acusa `macmon` ausente como item a
  corrigir (`brew install macmon`). Sem ele o app ainda funciona pelo estado do macOS.
- Testes (`tests/test_thermal.py`): leitor falso com sequência de estados/°C →
  pausa, histerese, cancelamento durante pausa, `max_wait_min`, modelo guardado
  chama o governador antes de gerar, sem `macmon` cai no estado do macOS.

## Item 3 · Manter o Mac acordado durante o trabalho

- Novo `core/keepawake.py`: enquanto análise ou render rodam, o app mantém
  `caffeinate -i -m -s -w <pid do app>` (impede sono ocioso, sono do disco e,
  na tomada, sono do sistema; a tela pode apagar). Encerrado ao terminar,
  cancelar ou fechar o app (`-w` garante mesmo se o app morrer).
- Usado em `ui/analysis_view.py::start_analysis`, `ui/delivery_view.py::process`
  e `cli.py analyze`.
- Selo na tela: “Mac mantido acordado”.
- Aviso na UI se estiver na bateria (`pmset -g batt`): “ligue na tomada para
  rodar por horas”.
- Testes com `subprocess` falso: inicia com o pid correto e encerra no fim/erro.

## Item 4 · Seletor “Rodar de madrugada” (sem senha)

Decisão da pessoa: tudo dentro da aplicação, **sem pedir senha e sem alterar
ajustes permanentes do macOS**.

- Novo `core/power.py` (só leitura + atalhos):
  - `power_checklist()` → itens com status ok/pendente e como resolver:
    na tomada (`pmset -g batt`), Modo de Baixo Consumo (`pmset -g` →
    `lowpowermode`), atualizações automáticas do macOS
    (`defaults read /Library/Preferences/com.apple.SoftwareUpdate
    AutomaticallyInstallMacOSUpdates`), tampa aberta (aviso fixo: o Air dorme com
    a tampa fechada sem monitor externo), `caffeinate` do VideoCut ativo
    (`pmset -g assertions`).
  - `open_settings(pane)` → `open "x-apple.systempreferences:<pane>"` para
    Bateria e Atualização de Software (identificadores confirmados na
    implementação para a versão do macOS instalada).
- `Project` ganha `overnight: bool` (padrão desligado); `cli.py analyze --overnight`.
- UI (`ui/material.py`, painel lateral): seletor **“Rodar de madrugada”**. Ligado:
  - usa o keep-awake do item 3 com `caffeinate -i -m -s` durante análise e render
    (a tela pode apagar; sistema e disco não dormem);
  - mostra o checklist ao vivo com ✓/◷ e botão “Abrir Ajustes” em cada pendência;
  - ao iniciar a análise com pendências críticas (bateria), confirma antes;
  - sugere ligar também o “Modo de cargas longas” (item 2).
- Análise/Entrega: selo “Madrugada · Mac mantido acordado” e, no fim, resumo com
  duração, pausas térmicas e se houve queda de energia/bateria.
- `videocut/docs/rodar-a-noite.md` curto, explicando o seletor e os ajustes que
  só a pessoa pode mudar (não há automação com senha).
- `make doctor` reutiliza `power_checklist()`.
- Testes (`tests/test_power.py`): parsing de `pmset -g`, `pmset -g batt`,
  `pmset -g assertions` e `defaults read` com saídas reais gravadas como fixture;
  checklist com cada item pendente; seletor liga keep-awake só com ele ativo.

## Item 5 · Acelerar a visão sem perder qualidade (depois do A/B)

- Acelerar a visão sem perder qualidade: remover do JSON campos nunca usados
  (`ambiente`, `plano`, `pessoas`, `apoio`), `max_tokens` 400, 1 chamada para
  takes < 5 s; perfil `rapido` (4B, detalhe limitado, frames 448 px) só após A/B
  no Episódio06 com `make compare` contra `reformandoOCarrocao.mp4`.

## Item 6 · Área de Configurações com os prompts editáveis

**Objetivo:** ver e editar, dentro do app, tudo o que é enviado aos modelos,
sem abrir arquivos no editor, com segurança para voltar ao padrão.

**Hoje** os textos ficam em arquivos lidos pelo código:

| Arquivo | Usado em | Controla |
|---|---|---|
| `prompts/visao_ampla.md` | `analysis/vision.py::load_prompt` | descrição dos frames (passagem ampla) |
| `prompts/visao_detalhe.md` | idem | sequência de frames (passagem detalhada) |
| `prompts/capitulos.md` | `story/planner.py` | divisão do dia em capítulos |
| `prompts/capitulo.md` | idem | escolha dos blocos de cada capítulo |
| `config/canal.yaml` | `story/planner.py::channel_context`, tela Material | regras do canal e formatos |
| `config/glossario.yaml` | `analysis/speech.py` | nomes e lugares para o Whisper |

**Proposta:**
- Nova etapa/aba **Configurações** (fora do fluxo 1–5, acessível pelo cabeçalho).
- Um editor por texto (`ui.codemirror` ou `ui.textarea` em fonte mono), com:
  descrição de para que serve, onde entra no fluxo e quais **variáveis** são
  obrigatórias (ex.: `{momentos}`, `{takes}`, `{intencao}`), validadas antes de
  salvar — um prompt sem `{momentos}` não pode ser salvo.
- **Prévia**: mostrar o prompt final montado com dados reais do projeto aberto
  (ex.: capítulo 1 do Episódio07), sem chamar o modelo.
- **Padrão preservado**: os arquivos do repositório continuam como padrão; as
  edições ficam em `~/.videocut/prompts/` (ou `videocut/.state/prompts/`, fora do
  git) e têm prioridade. Botões “Restaurar padrão” e “Comparar com o padrão”.
- **Histórico**: cada salvamento guarda uma versão com data; dá para voltar.
- **Aviso de cache**: mudar um prompt de visão invalida as descrições (refaz a
  análise visual); mudar os do planejador só refaz as histórias. A tela diz
  isso antes de salvar e sugere “Refazer histórias”.
- Remover o `lru_cache` de `core/config.py::load_yaml` (ou invalidá-lo ao salvar),
  para as edições valerem sem reiniciar o app.

**Pontos a decidir antes de implementar:**
- Edições globais (todas as pastas) ou por projeto? Sugestão: globais, com
  opção de sobrescrever por projeto depois.
- Incluir também `config/modelos.yaml` (amostragem, memória por modelo) e
  `config/execucao.yaml` (limites térmicos) como formulários, não texto livre?

**Verificação:** editar `capitulo.md`, ver a prévia, salvar, “Refazer histórias”
e conferir no cache (`analise/capituloNN__<hash>.json`) que o novo texto foi
usado; “Restaurar padrão” volta ao arquivo do repositório; testes para
validação de variáveis e prioridade usuário > padrão.

## Item 7 · Skills e agentes configuráveis

**Objetivo:** estender o que a IA faz sem mexer no código, criando e ativando
comportamentos na mesma área de Configurações.

**Definições propostas (a confirmar):**
- **Skill** = instrução reutilizável que muda *como* uma etapa existente pensa.
  Um arquivo Markdown com nome, descrição, etapa-alvo (`visao`, `capitulos`,
  `capitulo`) e o texto que é acrescentado ao prompt dessa etapa. Ex.: “Vlog
  rápido” (cortes curtos, sem falas longas), “Tutorial” (preservar passos em
  ordem), “Humor da família” (priorizar risadas e reações). Ativada por projeto,
  combinável com outras.
- **Agente** = etapa nova com prompt, modelo e entrada/saída próprios, rodando
  depois da análise ou do planejamento. Ex.: “Títulos e thumbnail” (sugere 5
  títulos e o melhor frame), “Revisor de ritmo” (aponta blocos lentos),
  “Capítulos do YouTube” (gera marcações de tempo para a descrição),
  “Checagem de fatos da família” (lista nomes e lugares citados para revisão).
  Resultado aparece como painel/arquivo extra na entrega; nunca altera a
  montagem sem aprovação.

**Proposta de implementação:**
- `skills/` e `agents/` como pastas de arquivos Markdown com frontmatter
  (`nome`, `descricao`, `etapa`/`entrada`, `saida`, `modelo`), padrão no repo +
  pasta do usuário, igual ao item 6.
- Registro que carrega e valida esses arquivos; skills inseridas nos prompts por
  um marcador (ex.: `{skills}`) nas etapas; agentes executados por um runner
  único que monta a entrada (inventário, proposta, plano) em JSON, chama o
  modelo local, valida a saída contra um schema simples e salva em
  `analise/agentes/<nome>.json`.
- UI: lista com ativar/desativar por projeto, editor (reaproveita o do item 6),
  “Testar agora” com o projeto aberto e tempo estimado.
- Tudo continua local e offline; um agente não pode escrever fora da pasta de
  saída (`core/safety.py`) nem alterar a montagem sem clique da pessoa.

**Pontos a decidir antes de implementar:**
- Quais 2–3 agentes vêm prontos na primeira versão?
- Agentes podem encadear (saída de um vira entrada de outro) ou só isolados no início?
- Formato compatível com skills do Claude Code (`SKILL.md` com frontmatter) para
  reaproveitar skills que você já tem, como `legendar-video` e `remover-silencio`?

**Verificação:** criar a skill “Vlog rápido”, ativar no Episódio07, “Refazer
histórias” e comparar duração média dos blocos; criar o agente “Títulos”, rodar
com a análise salva e ver o resultado na Entrega; testes para registro,
validação de frontmatter, injeção de skills e isolamento de escrita dos agentes.

## Verificação (itens 1–4)

- `make test` com os testes novos.
- Manual: ligar “Rodar de madrugada”, conferir checklist e atalhos dos Ajustes;
  `make doctor` (energia/térmico); rodar análise longa com o modo ligado e
  `pause_temp_c` baixo (ex. 60 °C) para forçar pausa → ver painel âmbar, retomada
  e total pausado; `pmset -g assertions` mostra o `caffeinate` durante e some ao
  terminar; desligar a tela 5 min e confirmar que a análise avança.
- Atualizar `CONTEXT.md`, `ARCHITECTURE.md` (invariantes: pausa térmica,
  keep-awake) e `PLANO.md`.
