# Registro de uso de IA

Usamos IA (Claude, via Claude Code) para ler o artigo, gerar e revisar o código da miniatura e revisar o texto do laudo. **Todos os números do laudo vêm das nossas execuções** (`logs/`), e cada um foi conferido contra o arquivo citado.

## Prompts mais importantes

| # | Prompt (resumo) | Aceito | Mudado | Descartado |
|---|-----------------|--------|--------|------------|
| 1 | "Leia o relatório oficial do incidente do Google Cloud de 12/06/2025 e resuma o mecanismo, com a linha do tempo e a seção de cada evento" | Mecanismo (política em branco → crash loop → efeito manada na recuperação) e a estrutura da linha do tempo | Conferimos cada parágrafo citado direto na página; adotamos o fim às 13:49 do Mini Incident Report e registramos a divergência com o cabeçalho (18:18) | Citações por "nº de parágrafo" que não conferimos na página |
| 2 | "Gere um docker-compose com 3 containers (banco de políticas, service control com N tarefas, cliente) que reproduza o crash loop e o efeito manada, com uma mitigação de backoff com jitter" | Arquitetura de 3 containers e 2 redes, banco como semáforo com fila e timeout, red-button por HTTP | Healthchecks com `condition: service_healthy`; parâmetros por variável de ambiente | — |
| 3 | "Revise as alterações, os logs e o laudo, verifique se cada número bate com os logs e crie um plano de ação" | Os 4 problemas críticos (ver erros 1 a 4 abaixo) e a ordem: corrigir a miniatura, rodar de novo e só então escrever | Acrescentamos o modo `exp` (backoff sem jitter) para separar o efeito do backoff do efeito do jitter | A "surpresa" anterior, que tinha saído de uma hipótese da própria IA e não dos logs (erro 2) |
| 4 | "Corrija a miniatura: `none` sem backoff, `/api` sorteando entre todas as tarefas, parada com 90% das tarefas prontas, % de erro em janela fixa e um `summarize.py` que indique o arquivo de cada mediana" | Todas as mudanças; `summarize.py` passou a ser a única fonte dos números do laudo | Corrigimos o critério de parada depois do teste (erro 5) | — |
| 5 | "Analise o APIManuali e indique arquivo e trecho onde o mesmo mecanismo pode aparecer" | `atualizar` (campos em branco), `/health` sem verificação, fila serial global e conexão ao banco sem backoff | Rodamos o PUT parcial de verdade antes de citar (`logs/parte_d_apimanuali/put_parcial.log`); o `/health` foi um ponto que acrescentamos | A afirmação de que a fila serial "já sobrecarrega hoje": as tarefas são síncronas e a fila esvazia na hora, então citamos como risco da migração |

## Erros da IA encontrados ao rodar o código e conferir os logs

**1. O modo `none` ganhou backoff exponencial sem querer.**
- **Onde:** a mudança do commit `eeba790` fez `restart_delay()` retornar `min(CAPB, RESTART * 2**c)` em qualquer modo que não fosse `jitter`. Dá para ver com `git show f1c4151:app/service_control.py`, linhas 91-96.
- **Como percebemos:** a comparação ficou "com jitter contra sem jitter", e não "com backoff contra sem backoff". Por isso a diferença entre os modos parecia pequena: recuperação de 3,91 a 4,31 s no `none` da v1 (`logs/v1/none_run*/metrics.txt`).
- **Correção:** a função `wait_time()` em `app/service_control.py` separa três modos: `none` com `RESTART` fixo, `exp` com backoff sem jitter e `jitter`. Com o `none` corrigido, a recuperação passou para 63,49 s (`logs/none_run1/metrics.txt`).

**2. A "surpresa" do laudo era contradita pelos próprios logs.**
- **O erro:** o laudo da v1 dizia que o banco já ficava sobrecarregado durante o crash loop, antes do red-button. Esse texto saiu de uma hipótese levantada pela IA, não de uma medição.
- **Como percebemos:** separamos o `db.log` por fase. Em todas as execuções da v1, a fila no crash loop é 0 e os picos (51, 251, 163) aparecem só depois do red-button (`logs/v1/none_run*/metrics_reanalise.txt`, linhas `pico_fila_no_db_*`).
- **Correção:** o `analyze.py` agora mede a carga do banco separada por fase, e a surpresa foi reescrita a partir do que os logs mostram.

**3. O `/api` declarava o sistema recuperado com metade da capacidade.**
- **O erro:** a IA fez o `/api` sortear só entre as tarefas *já prontas*, o que responde 200 se uma única tarefa em 100 estiver viva.
- **Como percebemos:** `logs/v1/none_run2/sc.log` termina com `ready_count=50`, mas `client_events.log` registra `stable_reached` e o `metrics.txt` informa recuperação de 3,91 s.
- **Correção:** o `/api` agora sorteia entre todas as N tarefas e falha se a sorteada não estiver pronta. O cliente só encerra com 90% das tarefas prontas por 20 s.

**4. Medianas citavam o arquivo de log errado.**
- **O erro:** no laudo da v1 (`git show f1c4151:docs/laudo_rascunho.md`, linhas 71-72), o pico de fila 163 e as 11 rejeições/s eram atribuídos a `logs/none_run2/metrics.txt`. Esse arquivo mostra 251 e 16. Os valores 163 e 11 estão em `logs/v1/none_run3/metrics.txt`.
- **Como aconteceu:** a IA escolheu a mediana certa, mas copiou o nome do run errado.
- **Correção:** criamos o `summarize.py`, que gera `logs/summary.txt` com a mediana e o arquivo de origem. Todos os números do laudo atual foram conferidos contra os logs por script.

**5. O cliente encerrava antes do fim da janela fixa de 60 s.**
- **O erro:** na primeira versão do novo critério de parada, a execução podia terminar logo depois de 20 s estáveis. Isso acontecia cerca de 55 s após o início, antes de `poison + 60 s`.
- **Como percebemos:** no teste rápido com Docker, o `metrics.txt` acusou `(execucao terminou antes do fim da janela)`. O mesmo aviso aparece ao reanalisar os runs da v1, que paravam cedo (`logs/v1/none_run*/metrics_reanalise.txt`, linha `erros_janela_fixa_60s_apos_poison_%`).
- **Correção:** `app/client.py` só encerra depois de `poison_injected + WINDOW_S + 1 s`. Nos 9 runs oficiais a janela ficou completa, sem o aviso.
