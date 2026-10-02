# Rodar o VideoCut de madrugada

Tudo acontece dentro do app, sem senha e sem alterar ajustes do macOS.

## No app

1. Tela **Material → painel Execução**: ligue **Rodar de madrugada**.
2. Ligue também o **Modo de cargas longas**: o Mac pausa para esfriar acima de
   95 °C (ou estado “sério” do macOS) e retoma abaixo de 80 °C.
3. Confira o checklist que aparece e use **Abrir Ajustes** nas pendências.
4. Clique em **Analisar conteúdo**. Na bateria, o app pede confirmação.

Durante a análise e o render o VideoCut mantém o Mac e o disco acordados
(`caffeinate -i -m -s`), mesmo que os ajustes de energia mandem dormir em
1 minuto. A tela pode apagar. Isso termina sozinho ao concluir, cancelar ou
fechar o app.

## O que o checklist confere

| Item | Por quê | Como resolver |
|---|---|---|
| Ligado na tomada | Análises longas esgotam a bateria | Conecte o carregador |
| Modo de Baixo Consumo desligado | Deixa a análise muito mais lenta | Ajustes → Bateria → Modo de Baixo Consumo: **Nunca** |
| Sem instalação automática do macOS | Atualizações podem reiniciar o Mac de madrugada | Ajustes → Geral → Atualização de Software → (i) em Atualizações Automáticas: desligue **Instalar atualizações do macOS** |
| Tampa aberta | Sem monitor externo, o Mac dorme ao fechar a tampa | Deixe aberta; a tela pode apagar |
| Mac mantido acordado | Confirma que o `caffeinate` do VideoCut está ativo | Automático durante análise e render |

## Pelo terminal

```bash
make doctor                                   # checklist de energia + temperatura
.venv/bin/python cli.py analyze /caminho/raw --overnight --long-run
```

## Se algo parar

O progresso é salvo a cada take. Abra o app, carregue a mesma pasta e clique
em Analisar: transcrições e descrições já feitas vêm do cache.
