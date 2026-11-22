#!/usr/bin/env python3
import csv
import re
import sys

if len(sys.argv) != 2:
    print("Uso: python3 analyze.py logs/<execucao>", file=sys.stderr)
    sys.exit(2)

d = sys.argv[1]


def read_events(path):
    ev = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                try:
                    ev[k.strip()] = float(v.strip())
                except ValueError:
                    continue
    except FileNotFoundError:
        pass
    return ev


def read_rows(path):
    rows = []
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append((float(r["epoch"]), int(r["status"]), float(r["latency_ms"])))
    except FileNotFoundError:
        pass
    return rows


def say(out, key, value, src):
    line = f"{key}: {value}   [fonte: {src}]"
    out.append(line)
    print(line)


def main():
    ev = read_events(f"{d}/client_events.log")
    rows = read_rows(f"{d}/client.csv")

    tp = ev.get("poison_injected")
    tr = ev.get("redbutton_pressed")
    tend = ev.get("end")

    out = []

    total = len(rows)
    say(out, "total_requisicoes", total, "client.csv")

    pre = [s for t, s, _ in rows if tp is None or t < tp]
    say(out, "erros_antes_da_falha_%",
        f"{100 * sum(s != 200 for s in pre) / max(1, len(pre)):.2f}" if pre else "N/A",
        "client.csv")

    if tp is None:
        say(out, "tempo_ate_falha_s", "N/A (politica nao injetada)", "client_events.log")
        say(out, "tempo_ate_recuperacao_s", "N/A", "client_events.log")
        say(out, "erros_na_janela_de_incidente_%", "N/A", "client.csv")
        say(out, "erros_apos_red-button_%", "N/A", "client.csv")
    else:
        errs_after_poison = [(t, s) for t, s, _ in rows if s != 200 and t >= tp]
        if not errs_after_poison:
            say(out, "tempo_ate_falha_s", "nenhum erro observado apos poison", "client.csv")
        else:
            first = errs_after_poison[0][0]
            say(out, "tempo_ate_falha_s (poison -> 1o erro)", f"{first - tp:.2f}",
                "client.csv + client_events.log")

        if tr is not None:
            errs_after_redbutton = [(t, s) for t, s, _ in rows if s != 200 and t >= tr]
            if not errs_after_redbutton:
                say(out, "tempo_ate_recuperacao_s (red-button -> ultimo erro)",
                    "0.00 (sem erros apos red-button)",
                    "client.csv + client_events.log")
            else:
                last = errs_after_redbutton[-1][0]
                rec = max(0.0, last - tr)
                censored = tend is not None and tend - last < 5
                say(out, "tempo_ate_recuperacao_s (red-button -> ultimo erro)",
                    f">{rec:.1f} (NAO recuperou ate o fim da execucao)" if censored else f"{rec:.2f}",
                    "client.csv + client_events.log")
        else:
            say(out, "tempo_ate_recuperacao_s", "N/A (red-button nao pressionado)", "client_events.log")

        last_err_overall = errs_after_poison[-1][0] if errs_after_poison else tp
        win = [s for t, s, _ in rows if tp <= t <= last_err_overall]
        say(out, "erros_na_janela_de_incidente_%",
            f"{100 * sum(s != 200 for s in win) / max(1, len(win)):.2f}" if win else "0.00",
            "client.csv")

        if tr is not None:
            post = [s for t, s, _ in rows if t >= tr]
            say(out, "erros_apos_red-button_%",
                f"{100 * sum(s != 200 for s in post) / max(1, len(post)):.2f}" if post else "0.00",
                "client.csv")
        else:
            say(out, "erros_apos_red-button_%", "N/A", "client.csv")

        ph = [s for t, s, _ in rows if tp <= t < (tr if tr is not None else float("inf"))]
        say(out, "erros_entre_poison_e_red-button_%",
            f"{100 * sum(s != 200 for s in ph) / max(1, len(ph)):.2f}" if ph else "0.00",
            "client.csv")

    rc = []
    try:
        with open(f"{d}/sc.log") as f:
            for line in f:
                m = re.match(r"(\d+\.\d+) ready_count=(\d+)", line)
                if m:
                    rc.append((float(m.group(1)), int(m.group(2))))
    except FileNotFoundError:
        pass

    n = max((c for _, c in rc), default=0)
    say(out, "tarefas_prontas_max (antes da falha)", n, "sc.log")

    if tr is not None and rc:
        for frac in (0.1, 0.5, 0.9):
            target = frac * n
            hit = [t for t, c in rc if t > tr and c >= target]
            if hit:
                say(out, f"tempo_ate_{int(frac * 100)}%_tarefas_prontas_s (red-button -> ready_count)",
                    f"{hit[0] - tr:.1f}", "sc.log")
            else:
                say(out, f"tempo_ate_{int(frac * 100)}%_tarefas_prontas_s (red-button -> ready_count)",
                    "nao atingiu ate o fim", "sc.log")

    rej = []
    wt = []
    try:
        with open(f"{d}/db.log") as f:
            for line in f:
                m = re.search(r"rej=(\d+)", line)
                if m:
                    rej.append(int(m.group(1)))
                m = re.search(r"waiting=(\d+)", line)
                if m:
                    wt.append(int(m.group(1)))
    except FileNotFoundError:
        pass

    say(out, "pico_leituras_rejeitadas_por_s_no_db", max(rej) if rej else 0, "db.log")
    say(out, "pico_fila_no_db", max(wt) if wt else 0, "db.log")

    with open(f"{d}/metrics.txt", "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
