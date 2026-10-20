# -*- coding: utf-8 -*-
"""
Extrapolación de Richardson generalizada para las series de convergencia de estudios_control.csv.

Para cada serie se ajusta, por mínimos cuadrados sobre todos los niveles disponibles,
    f(h) = f_inf - C * h**p,        h = 1/N  (malla lambda/N)
con p buscado en una rejilla fina y, para cada p, f_inf y C por mínimos cuadrados lineales.
Se informan p, f_inf, el residuo cuadrático medio (RMS) del ajuste y la predicción con dejar-uno-fuera
del nivel más fino a partir de los demás, como indicador de la estabilidad del ajuste.

    python extrapolacion.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SERIES = {
    "Dipolo de hilo de espesor nulo": "dipolo_malla{}",
    "Dipolo de sección 1 x 1 mm": "dipolo_seccion1mm_malla{}",
    "Parche en FR-4 ajustado": "parche_malla{}",
}


def ajuste(N, f):
    h = 1.0 / np.asarray(N, float)
    f = np.asarray(f, float)
    best = None
    for p in np.linspace(0.2, 4.0, 3801):
        A = np.column_stack([np.ones_like(h), -h ** p])
        (finf, C), *_ = np.linalg.lstsq(A, f, rcond=None)
        rms = np.sqrt(np.mean((A @ np.array([finf, C]) - f) ** 2))
        if best is None or rms < best[0]:
            best = (rms, p, finf, C)
    return best


def main():
    rows = {r["caso"]: r for r in csv.DictReader(open(HERE / "estudios_control.csv", encoding="utf-8"))}
    out = []
    for nombre, pat in SERIES.items():
        N = [n for n in (20, 30, 40, 80, 120, 160) if pat.format(n) in rows and rows[pat.format(n)]["f_res_mhz"]]
        f = [float(rows[pat.format(n)]["f_res_mhz"]) for n in N]
        rms, p, finf, C = ajuste(N, f)
        loo = ""
        if len(N) >= 4:
            _, p2, finf2, C2 = ajuste(N[:-1], f[:-1])
            pred = finf2 - C2 * (1.0 / N[-1]) ** p2
            loo = f"{pred:.1f} (observado {f[-1]:.1f})"
        cambios = [100 * (b - a) / a for a, b in zip(f, f[1:])]
        out.append(dict(serie=nombre, niveles=" ".join(f"lambda/{n}" for n in N), p=round(p, 2), f_inf_mhz=round(finf, 1),
                        rms_mhz=round(rms, 2), prediccion_nivel_mas_fino=loo,
                        cambio_ultimo_pct=round(cambios[-1], 2), distancia_referencia_pct=""))
        print(f"{nombre}: niveles {N}\n  p = {p:.2f}  f_inf = {finf:.1f} MHz  RMS = {rms:.2f} MHz  "
              f"cambios sucesivos (%) = {[round(c, 2) for c in cambios]}  LOO nivel más fino: {loo}")
    with open(HERE / "extrapolacion.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
