# Plano de implementação do VideoCut

Branch: `feat/videocut`. Cada fase é autocontida: termina com `make test` verde e
um commit `feat(videocut): fase N ...`. Para retomar, leia a primeira fase sem
`[x]`, o registro abaixo e `CONTEXT.md`.

Referência de interface: `../VideoCut — wireframe de montagem por conteúdo.html`
(estudo em `../designs/videocut/`).

## Fases

- [x] **1. Fundação** — pasta isolada, venv, Makefile, schemas, projeto persistido, cache
- [x] **2. Mídia** — ffprobe, miniaturas, amostragem de frames, mudanças de cena, áudio e proxies
- [x] **3. Fala** — Whisper MLX com palavras, frases, glossário e cache
- [x] **4. Visão** — MLX-VLM/Qwen3-VL, passagem ampla + detalhada, JSON, cache por modelo
- [x] **5. Histórias** — inventário, planejador editorial, propostas, suficiência, validador
- [x] **6. Montagem e render** — faixas de imagem/áudio, B-roll, crossfades, formato, ffmpeg, SRT, relatório
- [x] **7. Timeline Filmora** — XML editável e pacote de entrega
- [x] **8. UI Material + Análise** — telas 1–2, análise em background por take
- [x] **9. UI Histórias + Revisão** — telas 3–4, evidências, blocos, troca de vídeo, versão mais curta
- [x] **10. UI Entrega** — tela 5, render em background, relatório em formação
- [x] **11. Prova com episódio real** — comparador com edição existente, benchmark 4B × 8B, doctor, docs

## Registro

| Fase | Situação | Observações |
|---|---|---|
| 1 | concluída | Mac de referência: Apple M5, 24 GB. Mudança de cena via filtro `scene` do ffmpeg (sem OpenCV). |
| 2 | concluída | `media/`: probe com rotação, catálogo que preserva ids, frames em cache, cenas via ffmpeg, WAV 16 kHz, proxy H.264. |
| 3 | concluída | `analysis/speech.py`: Whisper MLX, frases por pontuação/pausa, cache por modelo+glossário, `release_model()`. Smoke test real ok (5,6 s). |
| 4 | concluída | `analysis/vlm.py` (MlxModel + JSON tolerante com nova tentativa), `analysis/vision.py` (ampla + detalhe). Repos confirmados no HF: 4B 3,1 GB, 8B 5,8 GB. Pesos ainda não baixados: smoke test real fica para a fase 11, com autorização. |
| 5 | concluída | Inventário por momentos citáveis (`T05.03`), `prompts/historias.md`, `config/canal.yaml` editável, validador anti-invenção, critérios estruturais (o mais severo vence), cache da resposta bruta, `shorten()` sem modelo. |
| 6 | concluída | Render por segmento (1 por bloco, `-ss/-t` na entrada, cache por posição relativa: reordenar reaproveita) + concat sem recodificar. VideoToolbox no Mac. Formato pela maioria (orientação/FPS NTSC), pillarbox. Ambiente do B-roll a −22 dB, fades de 80 ms. SRT remapeado, relatório Markdown. |
| 2b | concluída | Proxies `.LRF` da câmera (mesmo nome, duração ±1 s) viram `Take.proxy`; `analysis_path` usado em miniatura, cenas e frames. Render sempre usa o original. Na UI (fase 8), servir `.LRF` como `video/mp4` e usar áudio do LRF com fallback para o original. |
| 7 | concluída | FCP7 XML (xmeml v5): V1 blocos, V2 B-roll, A1 fala/ambiente, A2 ambiente do B-roll com Audio Levels. Guia Mac do Filmora só cita “Importar Timeline XML”; formato escolhido porque o Filmora exporta FCP7 XML. **Validar importação real na fase 11.** `montage/delivery.py` grava documentos antes do render. |
| 8 | concluída | `analysis/pipeline.py` (Whisper em todos → libera → VLM → planejador, cancelável, falha por take). UI: `ui/shell.py` (moldura, `notify` no root para callbacks pós-await), `material.py`, `analysis_view.py`, `/media/<chave>` (LRF como video/mp4). `make ui` → http://localhost:8090. Verificado no navegador com Whisper real + modelo visual roteirizado (script de demo fora do repo). |
| 9 | concluída | `stories.py` (veredito, lacunas, propostas, critérios com evidência, itens descartados), `review.py` (faixas imagem/apoio/áudio, excluir/restaurar/mover/proteger, ±frase, trocar trecho, versão mais curta, restaurar original), `evidence.py` e `player.js` (prévia da sequência com B-roll sobreposto, sem render). Verificado no navegador. |
| 10 | concluída | `delivery_view.py`: render em background por vídeo, cronômetro, progresso, falha isolada por vídeo, card vira relatório com Assistir/MP4/Relatório/XML/SRT/Plano (revela no Finder). `project.renders` persistido e invalidado ao editar a revisão. Verificado no navegador: 20 s em 1080p em ~2 s. |
| 11 | concluída (ferramentas) | `proof/compare.py` (alinha falas da edição final com os takes: recall, precisão, ordem), `proof/benchmark.py` (tempo, memória de pico, JSON inválido, descrições lado a lado), `cli.py` + `make doctor/analyze/compare/benchmark`. Sanidade: montagem × ela mesma = 100%. |

## Pendências que dependem de você

1. Autorizar o download do Qwen3-VL (4B 3,1 GB e/ou 8B 5,8 GB) — primeira análise real ou `make benchmark`.
2. Rodar `make analyze` + `make compare` com um episódio já editado para medir a proposta contra a sua edição.
3. Importar um `timelines/*__timeline.xml` no seu Filmora e confirmar se V1/V2/A1/A2 chegam corretos.
4. Ajustar `config/canal.yaml` e `prompts/historias.md` a partir do que a comparação mostrar.

## Próximos passos

Ver `BACKLOG.md`: takes curtos, modo de cargas longas (pausa térmica), Mac acordado, seletor “Rodar de madrugada” e aceleração da visão. Implementar quando pedido (“implementa o backlog”).
