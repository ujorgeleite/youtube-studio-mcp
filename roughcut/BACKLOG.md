# Backlog

## Resumo de duração e resultado de uma execução

Criar, ao final de cada análise ou processamento, um resumo visual do lote para
mostrar o efeito prático do trabalho realizado.

- Exibir um cronômetro desde o início da análise e outro desde o início da
  renderização.
- Mostrar a duração total de processamento, com o tempo gasto por vídeo e por
  etapa quando disponível.
- Consolidar vídeos selecionados, analisados, renderizados, ignorados por não
  terem áudio e vídeos que falharam.
- Comparar duração original, duração final e tempo de vídeo removido em todo o
  lote.
- Mostrar a relação entre o tempo de vídeo removido e o tempo investido pelo
  computador no processamento. Essa relação é uma referência operacional; não
  representa automaticamente o tempo humano de edição economizado.
- Oferecer um relatório visual ao término, com links para os vídeos, timelines,
  legendas e relatórios gerados.
- Salvar uma cópia estruturada do resumo em `reports/` para consulta posterior.
- Construir o relatório de forma incremental: quando cada vídeo terminar, criar
  imediatamente sua linha no relatório com status, durações, cortes e links de
  saída disponíveis.
- Retirar da lista operacional os vídeos concluídos, ignorados ou com falha e
  manter suas informações acessíveis no relatório em formação. A tela principal
  fica focada somente nos itens ainda em análise ou renderização.

Status: implementado na interface e em `smartcut/batch_report.py`. Uma futura
evolução pode adicionar estimativa configurável de tempo humano de edição.
