#!/usr/bin/env python3
"""Gera docs/laudo.pdf a partir de docs/laudo.md.

Requisitos: pacote `markdown` (pip install markdown) e Microsoft Edge ou
Google Chrome instalado (usado em modo headless para imprimir o PDF).

Uso: python docs/gerar_pdf.py
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import markdown

DOCS = pathlib.Path(__file__).resolve().parent
SRC = DOCS / "laudo.md"
HTML = DOCS / "laudo.html"
PDF = DOCS / "laudo.pdf"

CSS = """
@page { size: A4; margin: 14mm 14mm 14mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.6pt; line-height: 1.35; color: #111; }
h1 { font-size: 15pt; margin: 0 0 4pt 0; }
h2 { font-size: 12pt; margin: 10pt 0 4pt 0; border-bottom: 1px solid #999; padding-bottom: 2pt;
     break-after: avoid; page-break-after: avoid; }
h2 + p:has(img) { break-before: avoid; }
h2:has(+ p > img) { break-before: page; }
p { margin: 3pt 0 5pt 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 7pt 0; font-size: 8.4pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 2.5pt 4pt; vertical-align: top; text-align: left; }
th { background: #eee; }
code { font-family: Consolas, monospace; font-size: 8.2pt; background: #f3f3f3; padding: 0 2px; }
pre { background: #f3f3f3; padding: 4pt 6pt; margin: 3pt 0 6pt 0; font-size: 8pt; line-height: 1.25; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { display: block; max-width: 82%; margin: 4pt auto; }
hr { display: none; }
"""


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            candidates.insert(0, p)
    for c in candidates:
        if os.path.isfile(c):
            return c
    sys.exit("Edge/Chrome nao encontrado para gerar o PDF.")


def main():
    body = markdown.markdown(SRC.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    HTML.write_text(
        f'<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
        f"<title>Laudo - incidente Google Cloud</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>",
        encoding="utf-8",
    )
    if PDF.exists():
        PDF.unlink()
    # Perfil temporario separado: sem ele, um Edge/Chrome ja aberto absorve o
    # comando e o PDF nao e gravado.
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", f"--print-to-pdf={PDF}", HTML.as_uri()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
    HTML.unlink()
    if not PDF.exists():
        sys.exit("O navegador nao gerou o PDF.")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", PDF.read_bytes()))
    print(f"{PDF.name}: {pages} pagina(s)")
    if pages > 6:
        print("ATENCAO: o limite da entrega e 6 paginas.")


if __name__ == "__main__":
    main()
