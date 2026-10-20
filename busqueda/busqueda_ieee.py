# -*- coding: utf-8 -*-
"""Descarga TODOS los registros de IEEE Xplore (todos los metadatos, 2020-2026) para S1-S3 y S4b."""
import json, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
H = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*", "Origin": "https://ieeexplore.ieee.org",
     "Referer": "https://ieeexplore.ieee.org/search/searchresult.jsp",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}
Q = json.load(open("consultas.json", encoding="utf-8"))
recs = []
for k, q in Q.items():
    page, got, total = 1, 0, 1
    while got < total:
        body = json.dumps({"queryText": q, "highlight": False, "returnFacets": ["ALL"], "returnType": "SEARCH", "matchPubs": True,
                           "ranges": ["2020_2026_Year"], "rowsPerPage": 100, "pageNumber": page}).encode()
        j = json.loads(urllib.request.urlopen(urllib.request.Request("https://ieeexplore.ieee.org/rest/search", data=body, headers=H), timeout=90).read())
        total = j.get("totalRecords", 0)
        rs = j.get("records") or []
        for x in rs:
            recs.append(dict(base="IEEE Xplore", consulta=k, id=x.get("articleNumber"), doi=(x.get("doi") or "").lower(),
                             anio=x.get("publicationYear"), titulo=x.get("articleTitle") or "", fuente=x.get("publicationTitle") or "",
                             tipo=x.get("contentType") or "", resumen=(x.get("abstract") or "")[:1500]))
        got += len(rs); page += 1
        if not rs: break
        time.sleep(1.5)
    print(k, got, "de", total)
json.dump(recs, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("total", len(recs))
