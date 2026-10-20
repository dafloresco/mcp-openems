# -*- coding: utf-8 -*-
"""Búsqueda documentada, segunda versión: descarga TODOS los registros de OpenAlex y ERIC para S1-S3 y S4b."""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "ridu-revision/2.0 (mailto:dflores@unp.edu.pe)"}
Q = {
    "S1": '("AI agent" OR "LLM agent" OR "agentic AI" OR "Model Context Protocol") AND (education OR teaching) AND (engineering OR simulation)',
    "S2": '("large language model" OR "generative AI" OR ChatGPT) AND "engineering education" AND (antenna OR electromagnetic OR simulation OR "circuit design")',
    "S3": '("intelligent tutoring" OR "AI tutor") AND engineering AND (simulation OR design)',
    "S4b": '("generative AI" OR "large language model") AND learning AND ("cognitive offloading" OR overreliance OR "over-reliance" OR "self-regulated") AND (engineering OR STEM)',
}


def get(url):
    for _ in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5)
    raise err


def inv(ab):
    if not ab:
        return ""
    pos = {}
    for w, ix in ab.items():
        for i in ix:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


recs = []
for k, q in Q.items():
    cursor, n = "*", 0
    while cursor:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode({
            "filter": f"title_and_abstract.search:{q},from_publication_date:2020-01-01,language:en|es",
            "per-page": 200, "cursor": cursor, "mailto": "dflores@unp.edu.pe"})
        j = get(url)
        for w in j["results"]:
            src = (w.get("primary_location") or {}).get("source") or {}
            recs.append(dict(base="OpenAlex", consulta=k, id=w["id"], doi=(w.get("doi") or "").replace("https://doi.org/", "").lower(),
                             anio=w.get("publication_year"), titulo=w.get("title") or "", fuente=src.get("display_name") or "",
                             tipo=w.get("type"), resumen=inv(w.get("abstract_inverted_index"))[:1500]))
            n += 1
        cursor = j["meta"].get("next_cursor")
        time.sleep(1)
    print(k, "OpenAlex", n, "de", j["meta"]["count"])
    url = "https://api.ies.ed.gov/eric/?" + urllib.parse.urlencode({
        "search": q + " AND publicationdateyear:[2020 TO 2026]", "format": "json", "rows": 2000,
        "fields": "id,title,publicationdateyear,source,doi,description,publicationtype"})
    j = get(url)
    for d in j["response"]["docs"]:
        recs.append(dict(base="ERIC", consulta=k, id=d.get("id"), doi=(d.get("doi") or "").replace("https://doi.org/", "").lower(),
                         anio=d.get("publicationdateyear"), titulo=d.get("title") or "", fuente=d.get("source") or "",
                         tipo=";".join(d.get("publicationtype") or []), resumen=(d.get("description") or "")[:1500]))
    print(k, "ERIC", len(j["response"]["docs"]), "de", j["response"]["numFound"])
json.dump(recs, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("total", len(recs))
