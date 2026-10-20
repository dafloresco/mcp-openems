# -*- coding: utf-8 -*-
"""
Simulación de potencia para el resultado principal (P1) con el modelo mixto previsto:
    y ~ modo + periodo + secuencia + pretest + (1 | estudiante)
Supuestos (puntajes estandarizados: varianza total del resultado = 1):
  - N reclutados = 36, asignados 18/18 a las secuencias ET y TE;
  - abandono del 15 % antes del periodo 2 (pérdida aleatoria): esos estudiantes aportan solo el periodo 1;
  - rho = correlación intraestudiante (proporción de varianza entre estudiantes): 0,3; 0,5; 0,7;
  - el pretest explica r^2 = 0,25 de la varianza entre estudiantes;
  - efecto de periodo (tarea) = 0,30 DE;
  - escenario de arrastre: haber estado en modo tutor en el periodo 1 suma 0,15 DE en el periodo 2.
Salida: potencia (proporción de p < 0,05 bilateral para el efecto del modo), sesgo medio del estimador
y potencia del análisis de sensibilidad del periodo 1 (regresión por mínimos cuadrados con el pretest).
"""
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
R = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
rng = np.random.default_rng(20261020)


def simula(tau, rho, arrastre=0.0, n=36, abandono=0.15, periodo=0.30):
    sec = np.repeat([0, 1], n // 2)  # 0 = ejecutor-tutor (ET), 1 = tutor-ejecutor (TE)
    pre = rng.normal(size=n)
    u = np.sqrt(rho) * (0.5 * pre + np.sqrt(1 - 0.25) * rng.normal(size=n))
    filas = []
    sigue = rng.random(n) >= abandono
    for i in range(n):
        for p in (1, 2):
            if p == 2 and not sigue[i]:
                continue
            tutor = int((sec[i] == 1) == (p == 1))
            mu = tau * tutor + periodo * (p == 2) + (arrastre if (p == 2 and sec[i] == 1) else 0.0)
            filas.append((i, p, sec[i], tutor, pre[i], mu + u[i] + np.sqrt(1 - rho) * rng.normal()))
    return pd.DataFrame(filas, columns=["id", "periodo", "secuencia", "tutor", "pre", "y"])


def una(tau, rho, arrastre):
    d = simula(tau, rho, arrastre)
    try:
        d["periodo2"] = (d.periodo == 2).astype(float)
        d["sec"] = d.secuencia.astype(float)
        m = smf.mixedlm("y ~ tutor + periodo2 + sec + pre", d, groups=d["id"]).fit(reml=True, method="bfgs")
        p, est = m.pvalues["tutor"], m.params["tutor"]
    except Exception:  # noqa: BLE001
        return np.nan, np.nan, np.nan
    d1 = d[d.periodo == 1]
    o = smf.ols("y ~ tutor + pre", d1).fit()
    return p, est, o.pvalues["tutor"]


def escenario(args):
    tau, rho, arrastre, semilla = args
    global rng
    rng = np.random.default_rng(semilla)
    res = np.array([una(tau, rho, arrastre) for _ in range(R)])
    ok = ~np.isnan(res[:, 0])
    return (tau, rho, arrastre, np.mean(res[ok, 0] < 0.05), np.mean(res[ok, 1]) - tau,
            np.mean(res[ok, 2] < 0.05), tau / np.sqrt(2 * (1 - rho)), int(ok.sum()))


if __name__ == "__main__":
    from multiprocessing import Pool
    tareas = [(tau, rho, arr, 1000 + i) for i, (arr, rho, tau) in enumerate(
        (a, r, t) for a in (0.0, 0.15) for r in (0.3, 0.5, 0.7) for t in (0.3, 0.4, 0.5, 0.6))]
    with Pool(12) as pool:
        filas = pool.map(escenario, tareas)
    import csv
    with open("potencia_resultados.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tau_DE", "rho", "arrastre", "potencia_mixto", "sesgo", "potencia_periodo1", "dz_equivalente", "replicas_validas"])
        for fila in filas:
            w.writerow([f"{x:.3f}" if isinstance(x, float) else x for x in fila])
    for fila in filas:
        print("%.1f %.1f %.2f | %.2f %+.3f | %.2f | %.2f (%d)" % fila, flush=True)
