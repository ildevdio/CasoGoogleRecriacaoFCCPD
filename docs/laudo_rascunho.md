# Laudo de Incidente Reproduzido — Google Cloud, 12/jun/2025

Equipe: SRE da disciplina | Repositório: https://github.com/ildevdio/CasoGoogleRecriacaoFCCPD | Fonte: https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW

---

## Parte A — O mecanismo

**Em uma frase:** uma política de cota com campos em branco (`quota: null`) foi replicada para todas as regiões em segundos e derrubou o Service Control, que rodava código novo sem tratamento de erro e sem feature flag; ao acionar o red-button, as tarefas de regiões grandes reiniciaram ao mesmo tempo, sem backoff exponencial aleatório, sobrecarregando o Spanner — um efeito manada (thundering herd).

A falha tem duas camadas:

| Camada | O que aconteceu | Conceito da disciplina |
|--------|-----------------|------------------------|
| Disparo (falha global) | Um dado inválido (`quota: null`) foi replicado globalmente "within seconds"; um null pointer jogou todas as regiões em crash loop simultâneo. | Acoplamento e ponto único de falha: um único dado ruim alcançou todas as regiões de uma vez, sem isolamento nem rollout em ondas. |
| Recuperação lenta | Em us-central1 as tarefas reiniciaram juntas, sem backoff exponencial aleatório, sobrecarregando o Spanner e prolongando a indisponibilidade. | Efeito manada (conceito principal): o artigo nomeia "herd effect" e aponta a falta de "randomized exponential backoff" como causa da sobrecarga. |

**Linha do tempo** (horários em US/Pacific, conforme o relatório oficial):

| # | Quando | Evento | Onde no artigo |
|---|--------|--------|----------------|
| 1 | 29/05/2025 | Nova checagem de cota entra no Service Control sem tratamento de erro e sem feature flag; caminho de código não exercitado no rollout regional | Incident Report › "What happened?", 2º parágrafo |
| 2 | 12/06 ~10:45 | Política com campos em branco gravada nas tabelas Spanner regionais e replicada globalmente em segundos; binários entram em crash loop | Incident Report › "What happened?", 3º parágrafo; status 11:46 (início 10:51) |
| 3 | ~+2 / +10 / +25 / +40 min | SRE em triagem; causa raiz identificada; red-button pronto; red-button aplicado e recuperação começa pelas regiões menores | Incident Report › "What happened?", 4º parágrafo |
| 4 | após o red-button | Em regiões grandes (us-central1) as tarefas reiniciam juntas, sem backoff exponencial aleatório, causando efeito manada no Spanner | Incident Report › "What happened?", 5º parágrafo |
| 5 | 12:48 | Todas as regiões exceto us-central1 mitigadas | Mini Incident Report (12 Jun 23:34) |
| 6 | até ~2h40 em us-central1 | Google limita a criação de tarefas e roteia tráfego para bancos multirregionais; fim do incidente 13:49 (mini relatório) | Incident Report, 5º parágrafo; Mini Incident Report |

**Inconsistência citada na fonte:** o cabeçalho da página marca o fim às 18:18 (impacto residual em Dataflow e Vertex AI), enquanto o mini relatório marca 13:49 e fala em "3 hours" de duração. Este laudo adota o **mini relatório (fim às 13:49)** como referência principal porque é o documento que trata especificamente do Service Control, o serviço afetado, enquanto o cabeçalho da página reflete impactos residuais em outros serviços.

**Conceito principal:** efeito manada (thundering herd). O próprio artigo usa o termo ("it created a herd effect on the underlying infrastructure") e aponta a falta de "randomized exponential backoff" como causa da sobrecarga do Spanner durante a recuperação.

**Conceito secundário:** acoplamento/consistência. A replicação global quase instantânea da política ruim atingiu todas as regiões ao mesmo tempo, sem rollout em ondas, transformando um problema local em falha global.

---

## Parte B — A miniatura

**Diagrama:** `client → [frontend] → service-control → [backend] → policy-db`; o `client` também está na rede `backend` para injetar a política.

![Diagrama da miniatura: containers e redes](docs/diagrama_miniatura.svg)

| Container | Representa no sistema real |
|-----------|----------------------------|
| `policy-db` | Tabelas regionais do Spanner com políticas de cota (capacidade limitada de leituras simultâneas) |
| `service-control` | Binário Service Control (100 tarefas em threads, crash loop com `quota=null`, red-button para desligar caminho defeituoso) |
| `client` | Tráfego de API de clientes + operador de produção (injeta a política ruim e aciona o red-button) |

**O que a miniatura NÃO reproduz** (com efeito nas conclusões):

| Ponto real não reproduzido | Efeito nas conclusões |
|---------------------------|----------------------|
| Replicação global entre dezenas de regiões (aqui há 1 "região") | Não é possível mostrar a recuperação escalonada das regiões menores primeiro nem o impacto diferenciado entre regiões grandes e pequenas. |
| Spanner real (réplicas, autoscaling); aqui o banco é um semáforo com custo fixo | Os tempos absolutos de sobrecarga e recuperação não são comparáveis numericamente ao Spanner; servem apenas para demonstrar o mecanismo qualitativo. |
| Escala (milhares de tarefas, tráfego real) e escala de tempo (minutos/horas viram segundos) | A proporção entre tempo de falha e tempo de recuperação é válida, mas os valores absolutos são comprimidos (horas viram segundos). |
| Falha do próprio monitoramento/status page (o artigo cita) | A miniatura não simula a queda da página de status, então não captura o impacto na comunicação com clientes durante o incidente. |

---

## Parte C — Experimento

Foram executadas 3 repetições por modo (`none` e `jitter`). Abaixo, a mediana de cada métrica com o arquivo de origem.

| Métrica | Miniatura (sem mitigação, `none`) | Arquivo-fonte | Miniatura (com mitigação, `jitter`) | Arquivo-fonte | Caso real (artigo) |
|---------|-----------------------------------|---------------|-------------------------------------|---------------|--------------------|
| Tempo até a falha | 2.95 s | `logs/none_run2/metrics.txt` | 2.95 s | `logs/jitter_run2/metrics.txt` | segundos (replicação "within seconds") |
| Tempo até a recuperação após o red-button | 4.10 s | `logs/none_run3/metrics.txt` | 0.31 s | `logs/jitter_run1/metrics.txt` | ~40 min até começar; até ~2h40 em us-central1 |
| % de requisições com erro (janela do incidente) | 66.49% | `logs/none_run2/metrics.txt` | 81.82% | `logs/jitter_run2/metrics.txt` | não informado no artigo |
| % de requisições com erro após red-button | 1.82% | `logs/none_run1/metrics.txt` | 1.96% | `logs/jitter_run1/metrics.txt` | não informado no artigo |
| % de requisições com erro (entre poison e red-button) | 81.33% | `logs/none_run2/metrics.txt` | 81.33% | `logs/jitter_run2/metrics.txt` | não informado no artigo |
| Pico de fila no banco | 163 | `logs/none_run2/metrics.txt` | 21 | `logs/jitter_run1/metrics.txt` | não informado no artigo |
| Pico de leituras rejeitadas/s no banco | 11 | `logs/none_run2/metrics.txt` | 0 | `logs/jitter_run1/metrics.txt` | não informado no artigo |
| Tempo para 50% das tarefas prontas após red-button | 18.8 s | `logs/none_run2/metrics.txt` | 2.7 s | `logs/jitter_run2/metrics.txt` | não informado no artigo |
| Tempo para 90% das tarefas prontas após red-button | não atingiu até o fim | `logs/none_run2/metrics.txt` | 4.7 s | `logs/jitter_run3/metrics.txt` | não informado no artigo |

**Surpresa observada:** o banco já ficou sobrecarregado durante o crash loop (antes do red-button), não apenas na recuperação. Com 100 tarefas em crash loop fazendo polling a cada ~2s, a fila do banco chegou a 251 esperas simultâneas (`none_run2`) e 163 (`none_run3`), com até 16 leituras rejeitadas por segundo. Isso mostra que o mecanismo de falha começa antes do red-button: o crash loop em massa já sobrecarrega o banco, e o red-button apenas agrava ao sincronizar ainda mais as reinicializações. Esperávamos que o banco permanecesse saudável até o red-button, mas os logs mostram o oposto.

**Comparação com o artigo:** na miniatura, a recuperação sem mitigacao levou 4.10s contra 0.31s com jitter — uma redução de ~92%. No artigo, us-central1 levou até ~2h40 para se recuperar contra ~40 min para começar a recuperação em outras regiões. A proporção é similar: a falta de backoff na recuperação prolonga drasticamente a indisponibilidade, especialmente na região/escala maior.

---

## Parte D — Parecer

**Pode acontecer no nosso projeto?** Sim.

**Arquivo e trecho:** `app/service_control.py` (versão original, antes da correção), linhas do endpoint `/api`:

```python
if self.path == "/api":
    if count_ready() > 0:
        return self._send(200, {"ok": True})
    return self._send(503, {"error": "no ready task"})
```

**Por que:** bastava **uma** tarefa de 100 viva para todo o sistema parecer saudável (`200 OK`), mascarando a perda real de capacidade. Além disso, o reinício após crash usava `random.uniform(0, RESTART * 2)` sem backoff exponencial real, mantendo as tarefas sincronizadas — o mesmo efeito manada do incidente do Google Cloud. Se esse código estivesse sob carga com uma política ruim replicada, um crash loop em massa sobrecarregaria o banco exatamente como no incidente real.

**Mitigação implementada:** backoff exponencial com jitter por tarefa no reinício (`MITIGATION=jitter`, atraso `RESTART * 2^crashes` com teto e jitter) e `/api` sorteia uma tarefa pronta por requisição, refletindo a perda real de capacidade.

**Antes x Depois (mediana de 3 execuções):**

| Métrica | Sem mitigacao (`none`) | Com mitigacao (`jitter`) | Arquivo-fonte |
|---------|------------------------|--------------------------|---------------|
| Tempo até a falha | 2.95 s | 2.95 s | `logs/none_run2/metrics.txt`, `logs/jitter_run2/metrics.txt` |
| Tempo até a recuperação após red-button | 4.10 s | 0.31 s | `logs/none_run3/metrics.txt`, `logs/jitter_run1/metrics.txt` |
| % de erro na janela do incidente | 66.49% | 81.82% | `logs/none_run2/metrics.txt`, `logs/jitter_run2/metrics.txt` |
| % de erro após red-button | 1.82% | 1.96% | `logs/none_run1/metrics.txt`, `logs/jitter_run1/metrics.txt` |
| Pico de fila no banco | 163 | 21 | `logs/none_run2/metrics.txt`, `logs/jitter_run1/metrics.txt` |
| Tempo para 50% tarefas prontas após red-button | 18.8 s | 2.7 s | `logs/none_run2/metrics.txt`, `logs/jitter_run2/metrics.txt` |

**Parecer para a diretora:** Sim, esse mecanismo pode acontecer no nosso projeto. Qualquer serviço que (1) leia configuração sem validação, (2) entre em crash loop sem backoff, e (3) reinicie tarefas sincronizadas após um red-button, está sujeito ao mesmo efeito manada. A mitigação medida mostra que o backoff exponencial com jitter reduz o tempo de recuperação em mais de 90% (de 4.10s para 0.31s na miniatura) e reduz o pico de fila do banco de 163 para 21. Recomendamos implementar backoff com jitter, validação de configuração com feature flag e rollout em ondas no projeto da equipe.

---

**Evidências:** todos os números acima têm correspondente em `logs/<modo>_run<N>/metrics.txt`, gerados por `analyze.py` a partir dos arquivos brutos `client.csv`, `client_events.log`, `sc.log` e `db.log`.
