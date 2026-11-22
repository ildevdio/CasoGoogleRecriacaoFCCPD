# Miniatura do incidente Google Cloud (12/06/2025)

Reproduz em 3 containers o mecanismo central do incidente: uma politica com campo em
branco derruba todas as tarefas do Service Control (crash loop) e, ao aplicar o
red-button, o reinicio simultaneo sem backoff sobrecarrega o banco (efeito manada).

## Requisitos
Docker + Docker Compose v2, Python 3 (so para `analyze.py`, sem dependencias externas).

## Passo a passo
```bash
# 1) Falha sem mitigacao (cada execucao leva ~1 a 4 min)
./run.sh none 1
# 2) Mesma falha com backoff exponencial + jitter
./run.sh jitter 1
```
Cada execucao cria `logs/<modo>_run<N>/` com: `client.csv` (cada requisicao),
`client_events.log` (instantes de injecao da politica e do red-button), `sc.log`,
`db.log`, `compose_stdout.log` e `metrics.txt` (gerado por `analyze.py`).
Repita 3x cada modo (`./run.sh none 2`, ...) e use a mediana no laudo.

## O que acontece (linha do tempo da execucao)
- t=0: sistema saudavel, 50 req/s.
- t=20 s: politica com `quota: null` e gravada no banco (= politica com campos em branco).
  As tarefas leem, "dereferenciam null" e caem em crash loop -> HTTP 503.
- t=35 s: red-button desliga o caminho de codigo defeituoso; todas as tarefas reiniciam
  juntas e releem o banco -> sobrecarga (sem mitigacao) ate o sistema se recuperar.
- Fim: apos 20 s sem erros ou em MAX_S.

## Metricas (analyze.py)
tempo ate a falha, tempo ate a recuperacao, % de requisicoes com erro, pico de fila no
banco; cada linha de `metrics.txt` indica o arquivo-fonte.

## Parametros
Variaveis de ambiente no `docker-compose.yml` (`DB_CAPACITY`, `DB_COST_MS`, `N_TASKS`,
`WARMUP_READS`, `POISON_AT_S`, `REDBUTTON_AT_S`...). Exemplo:
`DB_COST_MS=60 ./run.sh none 1`.

## Estrutura
`docker-compose.yml` · `Dockerfile` · `app/{db,service_control,client}.py` ·
`run.sh` · `analyze.py` · `logs/` · `IA.md` · `docs/` (diagrama da miniatura e rascunho do laudo)
