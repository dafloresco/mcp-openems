# Búsqueda bibliográfica documentada

Archivos de la revisión narrativa con búsqueda documentada del artículo (búsqueda del 20 de octubre de 2026).

| Archivo | Contenido |
|---|---|
| `consultas.json` | Ecuaciones S1–S4 exactas |
| `busqueda_openalex_eric.py` | Descarga todos los registros de OpenAlex (título y resumen, 2020–2026, inglés o español) y de ERIC |
| `busqueda_ieee.py` | Descarga todos los registros de IEEE Xplore (todos los metadatos, 2020–2026) |
| `deduplicar.py` | Une las tres bases y elimina duplicados por DOI y por título normalizado |
| `candidatos.txt` | Números de los 178 registros que pasaron el cribado por título |
| `decisiones.py` | Decisiones del cribado por resumen (incluidos con categoría y aporte; excluidos con motivo) y generación de `cribado.csv` |
| `cribado.csv` | Los 1216 registros únicos con base, ecuación, etapa de decisión, decisión y motivo o aporte |

Flujo: 1332 registros → 116 duplicados → 1216 únicos → 1038 excluidos por título → 178 resúmenes leídos → 116 excluidos con motivo → **62 incluidos**.

No se publican los resúmenes de los registros, protegidos por derechos de autor de sus editores. Al volver a ejecutar los scripts se descargan localmente. Los resultados de las bases cambian con el tiempo, así que una ejecución posterior puede no coincidir exactamente.

El cribado lo realizó un único revisor (el autor) con asistencia de un modelo de lenguaje; no hubo doble cribado independiente.
