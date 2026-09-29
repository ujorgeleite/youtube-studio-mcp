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
- [ ] **9. UI Histórias + Revisão** — telas 3–4, evidências, blocos, troca de vídeo, versão mais curta
- [ ] **10. UI Entrega** — tela 5, render em background, relatório em formação
- [ ] **11. Prova com episódio real** — comparador com edição existente, benchmark 4B × 8B, doctor, docs

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
