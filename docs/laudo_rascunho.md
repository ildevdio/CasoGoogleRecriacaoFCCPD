# Laudo de Incidente Reproduzido — Google Cloud, 12/jun/2025
Equipe: ____ | Repositório: ____ | Fonte: https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW

## Parte A — O mecanismo
**Em uma frase:** uma política de cota com campos em branco foi replicada globalmente em segundos e
fez o Service Control (código novo, sem tratamento de erro e sem feature flag) entrar em crash loop
em todas as regiões; na recuperação, o reinício simultâneo das tarefas, sem backoff exponencial
aleatório, sobrecarregou o banco (Spanner), principalmente em us-central1.

**Linha do tempo** (horários em US/Pacific, conforme o relatório):
| # | Quando | Evento | Onde no artigo |
|---|--------|--------|----------------|
| 1 | 29/05/2025 | Nova checagem de cota entra no Service Control sem tratamento de erro e sem feature flag; o caminho de código não foi exercitado no rollout regional | Incident Report › "What happened?", 2º parágrafo |
| 2 | 12/06 ~10:45 | Política com campos em branco é gravada nas tabelas Spanner regionais e replicada globalmente em segundos; binários entram em crash loop | Incident Report › "What happened?", 3º parágrafo; status 11:46 (início 10:51) |
| 3 | ~+2 / +10 / +25 / +40 min | SRE em triagem; causa raiz identificada; red-button pronto; red-button aplicado e recuperação começa pelas regiões menores | Incident Report › "What happened?", 4º parágrafo |
| 4 | após o red-button | Em regiões grandes (us-central1) as tarefas reiniciam juntas e causam efeito manada no Spanner, sem backoff exponencial aleatório | Incident Report › "What happened?", 5º parágrafo |
| 5 | 12:48 | Todas as regiões exceto us-central1 mitigadas | Mini Incident Report (12 Jun 23:34) |
| 6 | até ~2h40 em us-central1 | Google limita a criação de tarefas e roteia tráfego para bancos multirregionais; fim do incidente 13:49 (mini relatório) | Incident Report, 5º parágrafo; Mini Incident Report |

> Atenção a uma inconsistência *dentro* da fonte: o cabeçalho da página marca o fim às 18:18 (impacto
> residual, ex.: Vertex AI), o mini relatório marca 13:49 e fala em 3 h de duração. Cite qual usa e por quê.

**Conceito:** *efeito manada* (thundering herd) como conceito principal — o artigo o nomeia
(“herd effect”) e a falta de backoff aleatório é a causa da sobrecarga. Conceito secundário:
*acoplamento/consistência* — a replicação global quase instantânea fez um dado ruim atingir todas as
regiões ao mesmo tempo, sem rollout em ondas. Justifiquem em 3–4 linhas com a evidência da linha 4.

## Parte B — A miniatura
(Diagrama: client → [frontend] → service-control → [backend] → policy-db; client também no backend.)
| Container | Representa no sistema real |
|---|---|
| policy-db | Tabelas regionais do Spanner com políticas/cotas (capacidade limitada) |
| service-control | Binário Service Control (100 tarefas em threads, com crash loop e red-button) |
| client | Tráfego de API de clientes + operador que injeta a política e aciona o red-button |

**O que a miniatura NÃO reproduz** (completem o “efeito nas conclusões”):
| Ponto real não reproduzido | Efeito nas conclusões |
|---|---|
| Replicação global entre dezenas de regiões (aqui há 1 “região”) | |
| Spanner real (réplicas, autoscaling); aqui o banco é um semáforo com custo fixo | |
| Escala (milhares de tarefas, tráfego real) e escala de tempo (minutos/horas viram segundos) | |
| Falha do próprio monitoramento/status page (o artigo cita) | |

## Parte C — Experimento
Preencher com `logs/*/metrics.txt` (3 execuções por modo; indicar o arquivo de cada número).
| Métrica | Miniatura (sem mitigação) | Arquivo | Caso real (artigo) |
|---|---|---|---|
| Tempo até a falha | | client.csv | segundos (replicação “within seconds”) |
| Tempo até a recuperação após o red-button | | client.csv | ~40 min até começar; até ~2h40 em us-central1 |
| % de requisições com erro | | client.csv | não informado no artigo |

**Surpresa:** descrevam algo que *vocês* observaram de diferente do esperado e a explicação.

## Parte D — Parecer
- Pode acontecer no nosso projeto? Sim. Arquivo/trecho: `app/service_control.py` (linhas 126-129 da versão original): o endpoint `/api` respondia `200` enquanto `count_ready() > 0`, ou seja, bastava **uma** tarefa de 100 viva para todo o sistema parecer saudável, mascarando a perda de capacidade. Além disso, o reinício após crash usava `random.uniform(0, RESTART * 2)` sem backoff exponencial real, mantendo as tarefas sincronizadas — o mesmo efeito manada do incidente do Google Cloud.
- Mitigação implementada: backoff exponencial com jitter por tarefa no reinício (`MITIGATION=jitter`) e `/api` sorteia uma tarefa pronta por requisição, refletindo a perda real de capacidade.
- Antes/depois (de `logs/none_run*` e `logs/jitter_run*`): preencher com as medianas de `metrics.txt` após rodar 3x cada modo.
