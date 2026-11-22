# Registro de uso de IA

## Prompts mais importantes (3 a 5)

| # | Prompt (resumo) | Aceito | Alterado | Descartado |
|---|-----------------|--------|----------|------------|
| 1 | Escolha do artigo e leitura do relatorio oficial do Google Cloud (12/jun/2025) | Sim | Nao | Nao |
| 2 | Gerar docker-compose + servicos da miniatura (db, service-control, client) reproduzindo crash loop e efeito manada | Sim | Adicionado healthchecks, dependencias ordenadas (condition: service_healthy) e redes separadas | Versao inicial sem healthcheck, que iniciava service-control antes do db estar pronto |
| 3 | Script de analise de metricas a partir dos logs (analyze.py) | Parcial | Reescrito: calculo de tempo de recuperacao usa so erros APOS o red-button (antes usava o ultimo erro geral, podendo ser anterior ao red-button e dar tempo negativo/zero); tratamento de linhas malformadas em client_events.log | Versao inicial que travara se client_events.log faltasse uma chave |
| 4 | Estrutura do laudo (Partes A-D) e rascunho do diagrama SVG | Sim | Ajustado para corresponder exatamente aos containers e nomes de endpoint do codigo | Nao |
| 5 | Mitigacao: backoff exponencial com jitter (MITIGATION=jitter) | Sim | Aplicado tanto nas leituras do DB quanto no restart das tarefas apos crash | Backoff apenas nas leituras (nao cobria o restart simultaneo apos o red-button) |

## Erros da IA encontrados ao rodar o codigo (minimo 2)

1. **Tempo de recuperacao invalido**: a primeira versao do analyze.py calculava `tempo_ate_recuperacao_s` como `ultimo_erro_geral - redbutton_pressed`. Como `ultimo_erro_geral` podia ser anterior ao red-button (erros entre poison e red-button), o resultado ficava negativo (ajustado para 0 com `max(0, ...)`) ou subestimado. Correcao: rastrear apenas erros ocorridos **após** o red-button para medir a recuperacao real.

2. **Condicao de corrida na lista `ready`**: a primeira versao do service_control.py escrevia `ready[i] = True/False` e lia `sum(ready)` nos manipuladores HTTP sem lock. Sob carga, `sum(ready)` podia ler a lista enquanto outra thread a modificava, produzindo contagem inconsistente e o endpoint `/ready` nunca retornando 200. Correcao: protegido com `threading.Lock()` (`ready_lock`) tanto nas escritas quanto nas leituras.

3. **Falta de healthcheck e ordenacao**: a versao inicial do docker-compose usava `depends_on` sem `condition: service_healthy`, então o service-control iniciava antes do policy-db estar ouvindo, causando falhas de warmup e atraso artificial no estado estável. Correcao: adicionado healthcheck em ambos e `condition: service_healthy` na dependencia.
