#!/usr/bin/env python3
"""Calcula as metricas a partir dos logs brutos de uma execucao.
Uso: python3 analyze.py logs/<execucao>"""
import csv, re, sys, os

d = sys.argv[1]
ev = dict(l.strip().split("=") for l in open(f"{d}/client_events.log"))
ev = {k: float(v) for k, v in ev.items()}
rows = [(float(r["epoch"]), int(r["status"]), float(r["latency_ms"]))
        for r in csv.DictReader(open(f"{d}/client.csv"))]
tp, tr, tend = ev["poison_injected"], ev["redbutton_pressed"], ev["end"]
errs = [(t, s) for t, s, _ in rows if s != 200 and t >= tp]
out = []
def say(k, v, src): out.append(f"{k}: {v}   [fonte: {src}]"); print(out[-1])

say("total_requisicoes", len(rows), "client.csv")
pre = [s for t, s, _ in rows if t < tp]
say("erros_antes_da_falha_%", f"{100*sum(s!=200 for s in pre)/max(1,len(pre)):.2f}", "client.csv")
if not errs:
    say("tempo_ate_falha_s", "nenhum erro observado", "client.csv")
else:
    first, last = errs[0][0], errs[-1][0]
    say("tempo_ate_falha_s (poison -> 1o erro)", f"{first-tp:.2f}", "client.csv + client_events.log")
    censored = tend - last < 5
    say("tempo_ate_recuperacao_s (red-button -> ultimo erro)",
        (f">{last-tr:.1f} (NAO recuperou ate o fim da execucao)" if censored else f"{max(0,last-tr):.2f}"),
        "client.csv + client_events.log")
    say("duracao_total_indisponibilidade_s (poison -> ultimo erro)", f"{last-tp:.2f}", "client.csv")
    win = [s for t, s, _ in rows if tp <= t <= last]
    say("erros_na_janela_de_incidente_%", f"{100*sum(s!=200 for s in win)/max(1,len(win)):.2f}", "client.csv")
    post = [s for t, s, _ in rows if t >= tr]
    say("erros_apos_red-button_%", f"{100*sum(s!=200 for s in post)/max(1,len(post)):.2f}", "client.csv")
    ph = [s for t, s, _ in rows if tp <= t < tr]
    say("erros_entre_poison_e_red-button_%", f"{100*sum(s!=200 for s in ph)/max(1,len(ph)):.2f}", "client.csv")
# service-control: retomada das tarefas apos o red-button
rc = [(float(m.group(1)), int(m.group(2))) for l in open(f"{d}/sc.log")
      if (m := re.match(r"(\d+\.\d+) ready_count=(\d+)", l))]
n = max(c for _, c in rc) if rc else 0
say("tarefas_prontas_max (antes da falha)", n, "sc.log")
for frac in (0.1, 0.5, 0.9):
    hit = [t for t, c in rc if t > tr and c >= frac * n]
    say(f"tempo_ate_{int(frac*100)}%_tarefas_prontas_s (red-button -> ready_count)",
        f"{hit[0]-tr:.1f}" if hit else "nao atingiu ate o fim", "sc.log")
rej = [int(m.group(1)) for l in open(f"{d}/db.log") if (m := re.search(r"rej=(\d+)", l))]
say("pico_leituras_rejeitadas_por_s_no_db", max(rej) if rej else 0, "db.log")
wt = [int(m.group(1)) for l in open(f"{d}/db.log") if (m := re.search(r"waiting=(\d+)", l))]
say("pico_fila_no_db", max(wt) if wt else 0, "db.log")
open(f"{d}/metrics.txt", "w").write("\n".join(out) + "\n")
