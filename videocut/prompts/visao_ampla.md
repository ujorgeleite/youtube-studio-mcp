Você observa frames de um take de vídeo caseiro de uma família brasileira.
As imagens estão em ordem temporal; os instantes são: {instantes}.
Arquivo: {arquivo}. Fala neste intervalo (transcrição, pode estar vazia): "{fala}"

Descreva somente o que é visível. Não invente nomes, sentimentos ou motivos.
Se algo for incerto, diga que é incerto.

Responda somente com um objeto JSON:
{{
  "descricao": "uma frase objetiva sobre o que aparece",
  "acao": "o que acontece ao longo dos frames, ou vazio se estático",
  "ambiente": "lugar visível (ex.: parque, cozinha, rua, carro)",
  "plano": "close | medio | aberto | detalhe | misto",
  "pessoas": ["descrição curta de cada pessoa visível, sem nomes"],
  "problemas": ["somente se houver: tremido, escuro, desfocado, obstruido, estourado, tela_preta"],
  "interesse": 0.0,
  "apoio": false
}}
"interesse" vai de 0 a 1: quanto o trecho mostra algo que prende a atenção
(ação, expressão, lugar marcante). "apoio" é true quando as imagens servem
para cobrir uma fala de outro take sem depender do próprio áudio.
