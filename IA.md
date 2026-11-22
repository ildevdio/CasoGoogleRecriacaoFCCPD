# Registro de uso de IA

> PREENCHER com o que REALMENTE aconteceu. Nao copie este modelo sem editar.

## Prompts mais importantes (3 a 5)
| # | Prompt (resumo) | Aceito | Alterado | Descartado |
|---|-----------------|--------|----------|------------|
| 1 | Escolha do artigo e leitura do relatorio oficial do Google | | | |
| 2 | Gerar docker-compose + servicos da miniatura (db, service-control, client) | | | |
| 3 | Script de analise de metricas a partir dos logs | | | |
| 4 | Estrutura do laudo (Partes A-D) | | | |

## Erros da IA encontrados ao rodar o codigo (minimo 2)
Candidatos que apareceram ao testar a primeira versao (confirme na SUA execucao antes de registrar):
1. **Colapso na inicializacao**: a primeira versao subia as 100 tarefas ao mesmo tempo e o
   banco ja ficava sobrecarregado antes da falha ser injetada (so ~24 tarefas prontas apos 60 s).
   Correcao: partida escalonada (`BOOT_STAGGER_S`) e o cliente so comeca a medir quando
   `/ready` indica todas as tarefas prontas.
2. **Falha nao se propagava**: tarefas ja prontas engoliam erros de leitura do banco e
   continuavam usando a politica em cache, entao a politica ruim nao era vista. Correcao:
   recalibrar a capacidade/custo do banco para ele nao rejeitar leituras em regime normal.
3. (adicione aqui qualquer erro novo que voces encontrarem)
