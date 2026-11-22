# Miniatura do incidente Google Cloud (12/06/2025)

## Artigo de origem

**O que é:** relatório oficial de incidente do Google Cloud, ocorrido em 12 de junho de 2025, no serviço Service Control. Uma política de cota com campos em branco (`quota: null`) foi gravada nas tabelas regionais do Spanner e replicada globalmente em segundos. Os binários do Service Control, que executavam código novo sem tratamento de erro e sem feature flag, leram a política ruim, entraram em `NullPointer` e caíram em crash loop em todas as regiões.

Ao aplicar o red-button (desligamento do caminho de código defeituoso), todas as tarefas reiniciaram ao mesmo tempo e releu o banco simultaneamente, sem backoff exponencial aleatório. Isso provocou um efeito manada (thundering herd) sobre o Spanner, sobrecarregando o banco e prolongando a recuperação, especialmente na região us-central1 (até cerca de 2h40).

**Fonte oficial:** https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW

**Objetivo de refazer este incidente:** verificar se o mesmo mecanismo — política ruim replicada globalmente, crash loop em massa e reinício simultâneo sem backoff causando efeito manada no banco — pode ocorrer no projeto da equipe da disciplina. A miniatura permite medir tempo até a falha, tempo até a recuperação e percentual de requisições com erro, comparando com o relato do artigo, e testar uma mitigacao (backoff com jitter) antes e depois.

---

## Requisitos

- Docker + Docker Compose v2
- Python 3 (apenas para `analyze.py`, sem dependências externas)

---

## Estrutura do repositório

```
docker-compose.yml   # orquestra os 3 containers e as redes
Dockerfile           # imagem base Python 3.12-slim com o app/
app/
  db.py              # policy-db  =  tabelas regionais do Spanner (capacidade limitada)
  service_control.py # service-control = binario Service Control (N tarefas em threads)
  client.py          # client     = trafego de API + operador (injeta politica, red-button)
run.sh               # script de execucao (./run.sh none|jitter [rep])
analyze.py           # calcula metricas a partir dos logs brutos
IA.md                # registro de uso de IA (prompts e erros corrigidos)
docs/
  diagrama_miniatura.svg  # diagrama de containers e redes
  laudo_rascunho.md       # rascunho do laudo tecnico (Partes A-D)
logs/                # saidas brutas das execucoes (gerado ao rodar)
```

---

## Arquitetura da miniatura

## Diagrama da miniatura (Parte B)

Três containers em duas redes Docker:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 460" font-family="Helvetica, Arial, sans-serif">
  <defs>
    <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#333"/>
    </marker>
  </defs>
  <rect width="800" height="460" fill="#fff"/>
  <text x="400" y="26" text-anchor="middle" font-size="17" font-weight="bold" fill="#111">Miniatura: containers e redes (docker-compose.yml)</text>

  <!-- redes -->
  <rect x="14" y="50" width="500" height="300" rx="14" fill="#e8f1fb" stroke="#4a7fb5" stroke-width="2" stroke-dasharray="8 4"/>
  <text x="26" y="72" font-size="13" font-weight="bold" fill="#2c5a8a">rede "frontend"</text>
  <rect x="286" y="50" width="500" height="300" rx="14" fill="#fdf0e1" stroke="#c9822b" stroke-width="2" stroke-dasharray="8 4" fill-opacity="0.55"/>
  <text x="774" y="72" text-anchor="end" font-size="13" font-weight="bold" fill="#9a5f12">rede "backend"</text>

  <!-- containers -->
  <rect x="34" y="150" width="190" height="110" rx="10" fill="#fff" stroke="#222" stroke-width="2"/>
  <text x="129" y="182" text-anchor="middle" font-size="15" font-weight="bold">client</text>
  <text x="129" y="204" text-anchor="middle" font-size="12">50 req/s em GET /api</text>
  <text x="129" y="222" text-anchor="middle" font-size="12">injeta a política ruim</text>
  <text x="129" y="240" text-anchor="middle" font-size="12">aciona o red-button</text>

  <rect x="305" y="150" width="190" height="110" rx="10" fill="#fff" stroke="#222" stroke-width="2"/>
  <text x="400" y="182" text-anchor="middle" font-size="15" font-weight="bold">service-control</text>
  <text x="400" y="204" text-anchor="middle" font-size="12">100 tarefas (threads)</text>
  <text x="400" y="222" text-anchor="middle" font-size="12">crash loop com quota=null</text>
  <text x="400" y="240" text-anchor="middle" font-size="12">retry com ou sem backoff</text>

  <rect x="575" y="150" width="190" height="110" rx="10" fill="#fff" stroke="#222" stroke-width="2"/>
  <text x="670" y="182" text-anchor="middle" font-size="15" font-weight="bold">policy-db</text>
  <text x="670" y="204" text-anchor="middle" font-size="12">10 leituras simultâneas</text>
  <text x="670" y="222" text-anchor="middle" font-size="12">80 ms por leitura</text>
  <text x="670" y="240" text-anchor="middle" font-size="12">fila: 503 após 2 s</text>

  <!-- setas -->
  <line x1="224" y1="190" x2="303" y2="190" stroke="#333" stroke-width="2" marker-end="url(#a)"/>
  <text x="264" y="182" text-anchor="middle" font-size="11">GET /api</text>
  <line x1="303" y1="228" x2="226" y2="228" stroke="#333" stroke-width="2" marker-end="url(#a)"/>
  <text x="264" y="244" text-anchor="middle" font-size="11">200 / 503</text>

  <line x1="495" y1="190" x2="573" y2="190" stroke="#333" stroke-width="2" marker-end="url(#a)"/>
  <text x="534" y="182" text-anchor="middle" font-size="11">GET /snapshot</text>

  <!-- red-button -->
  <path d="M129,150 L129,112 L400,112 L400,148" fill="none" stroke="#b02a2a" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#a)"/>
  <text x="264" y="106" text-anchor="middle" font-size="11" fill="#b02a2a">POST /redbutton (t = 35 s)</text>

  <!-- injeção -->
  <path d="M129,262 L129,312 L670,312 L670,262" fill="none" stroke="#b02a2a" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#a)"/>
  <text x="400" y="304" text-anchor="middle" font-size="11" fill="#b02a2a">POST /policy com quota=null (t = 20 s) — o client também está na rede backend</text>

  <!-- legenda real -->
  <text x="400" y="384" text-anchor="middle" font-size="12" font-weight="bold" fill="#111">Equivalência com o sistema real</text>
  <text x="400" y="404" text-anchor="middle" font-size="12">client = clientes da API + operador de produção  |  service-control = binário Service Control</text>
  <text x="400" y="422" text-anchor="middle" font-size="12">policy-db = tabelas regionais do Spanner  |  POST /redbutton = interruptor do caminho de código defeituoso</text>
  <text x="400" y="445" text-anchor="middle" font-size="11" fill="#555">Setas tracejadas vermelhas = eventos do roteiro do experimento (client.py)</text>
</svg>
```

| Container | Representa no sistema real |
|-----------|----------------------------|
| `policy-db` | Tabelas regionais do Spanner com políticas de cota (capacidade limitada de leituras simultâneas) |
| `service-control` | Binário Service Control (100 tarefas em threads, crash loop com `quota=null`, red-button para desligar caminho defeituoso) |
| `client` | Tráfego de API de clientes + operador de produção (injeta a política ruim e aciona o red-button) |

---

## Passo a passo para executar

### 1) Falha sem mitigacao (reproduz o incidente)

```bash
./run.sh none 1
```

Cada execução leva aproximadamente 1 a 4 minutos. Ao final, os logs brutos e métricas ficam em `logs/none_run1/`.

### 2) Mesma falha com mitigacao (backoff exponencial com jitter)

```bash
./run.sh jitter 1
```

Ao final, os logs ficam em `logs/jitter_run1/`.

### 3) Repetir para obter mediana (recomendado para o laudo)

O laudo deve usar a mediana de pelo menos 3 execuções por modo:

```bash
./run.sh none 2
./run.sh none 3
./run.sh jitter 2
./run.sh jitter 3
```

### 4) Personalizar parametros (opcional)

Variáveis de ambiente do `docker-compose.yml`:

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `MITIGATION` | `none` | `none` (sem mitigacao) ou `jitter` (backoff com jitter) |
| `N_TASKS` | `100` | Numero de tarefas do service-control |
| `DB_CAPACITY` | `10` | Leituras simultaneas permitidas no banco |
| `DB_COST_MS` | `80` | Custo (ms) de cada leitura no banco |
| `DB_QUEUE_TIMEOUT_S` | `2` | Timeout da fila do banco (503 apos esse tempo) |
| `WARMUP_READS` | `5` | Leituras de aquecimento por tarefa ao iniciar |
| `POISON_AT_S` | `20` | Segundo em que a politica ruim e injetada |
| `REDBUTTON_AT_S` | `35` | Segundo em que o red-button e acionado |
| `MAX_S` | `240` | Tempo maximo de execucao (segundos) |

Exemplo:
```bash
DB_COST_MS=60 ./run.sh none 1
```

---

## O que acontece durante a execucao (linha do tempo)

- **t = 0 s**: sistema saudável, 50 requisições por segundo, tarefas ficando prontas de forma escalonada.
- **t = 20 s**: política com `quota: null` gravada no `policy-db`. As tarefas do `service-control` leem a política, encontram `None`, disparam `NullPointer` e caem em crash loop → HTTP 503 em `/api`.
- **t = 35 s**: red-button acionado no `service-control`. As tarefas em crash loop reiniciam e releem o banco ao mesmo tempo. Sem mitigação (`none`), isso gera efeito manada sobre o banco até o sistema se recuperar. Com mitigação (`jitter`), o reinício é espaçado com backoff exponencial + jitter, reduzindo a sobrecarga.
- **Fim**: após 20 segundos consecutivos sem erro ou ao atingir `MAX_S` (240 s).

---

## Arquivos de log gerados por execucao

Cada execucao cria `logs/<modo>_run<N>/` com:

| Arquivo | Conteudo |
|---------|----------|
| `compose_stdout.log` | Saida bruta do Docker Compose |
| `client.csv` | Cada requisicao (epoch, status, latency_ms) |
| `client_events.log` | Instantes de injetar política e pressionar red-button |
| `sc.log` | service-control (task_ready, task_crash, ready_count por segundo) |
| `db.log` | policy-db (ok, rej, waiting por segundo) |
| `metrics.txt` | Metricas calculadas por `analyze.py`, cada uma com arquivo-fonte |

Todas as metricas em `metrics.txt` indicam o arquivo de origem (ex: `[fonte: client.csv]`). Todo número usado no laudo deve ter correspondente em `logs/`.

---

## Metricas calculadas (analyze.py)

- Tempo até a falha (poison → primeiro erro)
- Tempo até a recuperação após o red-button (red-button → último erro)
- Percentual de requisições com erro na janela do incidente
- Percentual de requisições com erro após o red-button
- Pico de leituras rejeitadas por segundo no banco
- Pico de fila no banco
- Quantidade máxima de tarefas prontas antes da falha
- Tempo para 10%, 50% e 90% das tarefas ficarem prontas após o red-button

---

## Comparacao com o artigo (para o laudo)

| Metrica | Miniatura | Caso real (artigo) |
|---------|-----------|--------------------|
| Tempo até a falha | segundos (após injecao da política) | replicação da política em segundos |
| Tempo até a recuperação | medido em `metrics.txt` | ~40 min até começar; até ~2h40 em us-central1 |
| Percentual de requisições com erro | medido em `metrics.txt` | não informado no artigo |

---

## Mitigacao implementada

A variável `MITIGATION=jitter` ativa:

- **Backoff exponencial com jitter** nas leituras do banco após erro (`random.uniform(0, min(CAPB, BASE * 2 ** attempt))`).
- **Reinicio com jitter** das tarefas após crash (`random.uniform(0, RESTART * 2)`).

Com `MITIGATION=none` (padrao), o reinicio é imediato (`RESTART` fixo), reproduzindo o efeito manada do incidente real.

Compare `logs/none_run*` com `logs/jitter_run*` para medir antes e depois da mitigacao.

---

## Para o professor reproduzir

```bash
# 1) Clonar o repositorio
# 2) Entrar na pasta
cd incident-lab

# 3) Rodar sem mitigacao
./run.sh none 1

# 4) Rodar com mitigacao
./run.sh jitter 1

# 5) Inspecionar logs e metricas em logs/
```

O `analyze.py` roda automaticamente ao final de cada `run.sh` e grava `metrics.txt` dentro da pasta da execucao.
