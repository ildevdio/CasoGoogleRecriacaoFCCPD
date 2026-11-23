#!/usr/bin/env python3
"""Junta os metrics.txt de todas as execucoes e grava logs/summary.txt.

Para cada modo (none, exp, jitter) e cada metrica, mostra a mediana das
repeticoes e o ARQUIVO de onde ela saiu. Com numero impar de repeticoes a
mediana e sempre o valor de uma execucao real, entao todo numero citado no
laudo pode ser conferido abrindo o arquivo indicado.

Uso: python3 summarize.py [pasta_de_logs]   (padrao: logs)
"""
import math
import os
import re
import sys

LOGS = sys.argv[1] if len(sys.argv) > 1 else "logs"
RUN_RE = re.compile(r"^(?P<mode>[a-z]+)_run(?P<rep>\d+)$")
MODE_ORDER = ["none", "exp", "jitter"]


def read_metrics(path):
    """Retorna lista ordenada de (metrica, valor_bruto) de um metrics.txt."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if ": " not in line:
                continue
            body = line.split("   [fonte:")[0]
            key, _, val = body.partition(": ")
            out.append((key.strip(), val.strip()))
    return out


def sort_key(raw):
    """Valor numerico para ordenar. Censurado (">x") ou 'nao atingiu' conta como pior."""
    m = re.match(r"^(-?\d+(?:\.\d+)?)", raw)
    if m:
        return float(m.group(1))
    if raw.startswith(">"):
        return math.inf
    if raw.startswith("nao atingiu"):
        return math.inf
    return None


def main():
    runs = {}
    for name in sorted(os.listdir(LOGS)):
        m = RUN_RE.match(name)
        path = os.path.join(LOGS, name, "metrics.txt")
        if m and os.path.isfile(path):
            runs.setdefault(m.group("mode"), []).append((int(m.group("rep")), name, path))

    if not runs:
        print(f"Nenhuma execucao <modo>_run<N>/metrics.txt encontrada em {LOGS}/", file=sys.stderr)
        sys.exit(1)

    modes = [m for m in MODE_ORDER if m in runs] + sorted(m for m in runs if m not in MODE_ORDER)
    lines = [
        "# Resumo das execucoes (gerado por summarize.py; nao editar a mao)",
        "# mediana = valor da execucao do meio; fonte = arquivo de onde o numero saiu",
        "",
    ]

    for mode in modes:
        reps = sorted(runs[mode])
        data = {name: dict(read_metrics(path)) for _, name, path in reps}
        keys = [k for k, _ in read_metrics(reps[0][2])]
        lines.append(f"== modo {mode} ({len(reps)} execucoes: {', '.join(n for _, n, _ in reps)})")
        if len(reps) % 2 == 0:
            lines.append("   AVISO: numero par de execucoes; a mediana abaixo e o valor inferior do meio")

        for key in keys:
            vals = [(name, data[name].get(key, "N/A")) for _, name, _ in reps]
            all_vals = "; ".join(f"{n}={v}" for n, v in vals)
            numeric = [(sort_key(v), n, v) for n, v in vals if sort_key(v) is not None]
            if len(numeric) == len(vals):
                numeric.sort(key=lambda x: x[0])
                _, src, med = numeric[(len(numeric) - 1) // 2]
                lines.append(f"{key}: mediana={med}   [fonte: {LOGS}/{src}/metrics.txt]")
            else:
                lines.append(f"{key}: (nao numerico)")
            lines.append(f"    valores: {all_vals}")
        lines.append("")

    out_path = os.path.join(LOGS, "summary.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    print(f"Gravado em {out_path}")


if __name__ == "__main__":
    main()
