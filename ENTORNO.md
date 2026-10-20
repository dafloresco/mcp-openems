# Entorno de cálculo del artículo

Resultados de la prueba técnica, de la prueba de permisos y de la extrapolación obtenidos el 19 y 20 de octubre de 2026 con:

| Elemento | Versión o especificación |
| --- | --- |
| Equipo | Computadora portátil Lenovo 83DV |
| Procesador | Intel Core i7-13650HX, 14 núcleos / 20 hilos |
| Memoria | 16 GB (15,7 GB utilizables) |
| Sistema operativo | Windows 11 Home 10.0.26200 |
| Python | 3.14.6 (64 bits) |
| openEMS / CSXCAD | 0.37.0 / 0.7.0 (distribución binaria para Windows) |
| SDK de MCP para Python | mcp 1.30.0 (protocolo 2025-11-25) |
| mcp-openems | 0.3.0 |
| Otras dependencias | ver `requirements-lock.txt` (numpy 2.5.4, h5py 3.16.0, matplotlib 3.11.2, psutil 7.2.2) |
| Simulador de contraste | CST Studio Suite 2025, solver temporal (licencia comercial; el modelo no se distribuye) |

Los tiempos de simulación dependen del equipo y de su carga. Las corridas se hicieron una tras otra, sin otras simulaciones en paralelo.

## Reproducir

```
python -m pip install -r requirements-lock.txt     # más openEMS 0.37.0 desde su distribución
python simulaciones/reproducir_tabla2.py           # siete casos de referencia
python simulaciones/estudios_control.py            # convergencia, repetición, contornos y pérdidas
python simulaciones/extrapolacion.py               # extrapolación de Richardson
python prueba_permisos.py                          # prueba de permisos del modo tutor
```

La simulación de potencia (`protocolo/`) se ejecutó con Python 3.12.10 y las versiones de `protocolo/requirements-estadistica.txt`.
