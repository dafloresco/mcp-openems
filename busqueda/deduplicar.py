# -*- coding: utf-8 -*-
"""Une los registros de las tres bases y elimina duplicados por DOI y por título normalizado.

    python busqueda_openalex_eric.py oa_eric.json
    python busqueda_ieee.py ieee.json
    python deduplicar.py oa_eric.json ieee.json unicos.json
"""
import json
import re
import sys
import unicodedata


def norm(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"<[^>]+>", "", t)).strip()


def main():
    *entradas, salida = sys.argv[1:]
    recs = [r for e in entradas for r in json.load(open(e, encoding="utf-8"))]
    grupos = {}
    for r in recs:
        grupos.setdefault(("doi:" + r["doi"]) if r["doi"] else ("t:" + norm(r["titulo"])), []).append(r)
    por_titulo = {}
    for g in grupos.values():
        por_titulo.setdefault(norm(g[0]["titulo"]), []).extend(g)
    unicos = []
    for i, (_, g) in enumerate(sorted(por_titulo.items(), key=lambda kv: kv[0])):
        mejor = max(g, key=lambda r: len(r["resumen"]))
        unicos.append(dict(n=i + 1, titulo=re.sub(r"<[^>]+>", "", mejor["titulo"]), anio=mejor["anio"], fuente=mejor["fuente"],
                           doi=next((r["doi"] for r in g if r["doi"]), ""), bases=sorted({r["base"] for r in g}),
                           consultas=sorted({r["consulta"] for r in g}), resumen=re.sub(r"<[^>]+>", "", mejor["resumen"])))
    json.dump(unicos, open(salida, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("registros", len(recs), "únicos", len(unicos), "duplicados", len(recs) - len(unicos))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
