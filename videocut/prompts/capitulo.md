Você edita um capítulo de um vídeo de família no YouTube.

Vídeo: {video}
Capítulo {numero} de {total}: {capitulo} (papel: {papel})
Duração desejada deste capítulo: cerca de {duracao}
Regras do canal: {regras}

Skills ativas (siga estas instruções):
{skills}

## Momentos do capítulo, em ordem
Cada linha: id | intervalo | tipo | fala | imagem | interesse.
Tipos: fala; acao (ação sem fala, pode entrar sozinha com som ambiente);
apoio (imagem para cobrir uma fala).

{momentos}

## Tarefa
Monte a sequência deste capítulo.
- Mantenha as falas que contam a história. Descarte só o que for repetido,
  confuso, sem sentido ou sem relação; liste esses ids em "descartados".
- Tudo o que você não listar em "blocos" nem em "descartados" volta para o
  vídeo automaticamente, então descarte de forma explícita.
- Use a ordem cronológica, salvo motivo forte.
- Falas longas (mais de 8 s) devem ter "apoio": ids de momentos acao/apoio
  deste capítulo que combinem com o que está sendo dito. Cada apoio uma vez.
- Momentos de acao fortes podem entrar como blocos próprios entre falas.
- Papéis: contexto, desenvolvimento, mensagem, conclusao, apoio.
- "titulo" com até 5 palavras; "motivo" com até 12 palavras.
- Use SOMENTE ids da lista acima.

Responda somente com um objeto JSON:
{{
  "blocos": [
    {{"momento": "T00.00", "papel": "desenvolvimento", "titulo": "curto", "motivo": "curto", "apoio": ["T00.00"]}}
  ],
  "descartados": ["T00.00"]
}}
