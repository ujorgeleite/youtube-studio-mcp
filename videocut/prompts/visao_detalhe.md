Você analisa uma sequência curta de frames de um take de vídeo caseiro,
em ordem temporal, nos instantes {instantes} (segundos do take {arquivo}).
Fala neste intervalo (pode estar vazia): "{fala}"
Descrição anterior, feita com poucos frames: "{anterior}"

Descreva a ação ao longo da sequência: o que começa, o que muda e como termina.
Aponte em qual frame (1 a {total}) a ação principal começa e termina.
Descreva somente o que é visível. Não invente nomes nem motivos.

Responda somente com um objeto JSON:
{{
  "descricao": "frase objetiva sobre o trecho",
  "acao": "a ação do início ao fim",
  "ambiente": "lugar visível",
  "plano": "close | medio | aberto | detalhe | misto",
  "pessoas": ["descrição curta, sem nomes"],
  "problemas": ["tremido, escuro, desfocado, obstruido, estourado, tela_preta — só se houver"],
  "inicio_frame": 1,
  "fim_frame": {total},
  "interesse": 0.0,
  "apoio": false
}}
