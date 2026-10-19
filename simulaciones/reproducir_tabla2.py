# -*- coding: utf-8 -*-
"""
Reproduce la tabla 2 del artículo: ejecuta cada simulación de esta carpeta y compara su
summary.json con los valores publicados (resultados_referencia.csv).

    python reproducir_tabla2.py                    # todas (unos 20-30 min en una portátil)
    python reproducir_tabla2.py dipolo_915         # solo algunas
    python reproducir_tabla2.py --solo-comparar    # compara resultados ya calculados

Necesita openEMS 0.37 con su interfaz de Python y CSXCAD_INSTALL_PATH definido.
"""
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Tolerancias: el criterio de parada de openEMS se evalúa a intervalos de tiempo, así que corridas idénticas
# pueden diferir ~0,1 % en frecuencia y varios dB en mínimos de S11 muy profundos (ver el artículo).
TOL_F_PCT, TOL_S11_DB, TOL_D_DB = 0.2, 3.0, 0.1


def num(x):
    return float(x) if x not in ("", None) else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only_compare = "--solo-comparar" in sys.argv
    ref = {r["caso"]: r for r in csv.DictReader(open(HERE / "resultados_referencia.csv", encoding="utf-8"))}
    cases = args or list(ref)
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8")
    ok_all = True
    print(f"{'caso':28} {'f_res MHz':>12} {'ref':>9} {'S11 dB':>8} {'ref':>7} {'D dBi':>6} {'ref':>6}  estado")
    for c in cases:
        d = HERE / c
        if not only_compare:
            t0 = time.time()
            r = subprocess.run([sys.executable, "simulate.py"], cwd=d, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode:
                print(f"{c:28} ERROR al simular:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
                ok_all = False
                continue
        f = d / "results" / "summary.json"
        if not f.exists():
            print(f"{c:28} sin resultados (ejecuta sin --solo-comparar)")
            ok_all = False
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        rf = ref[c]
        f_mhz, s11 = s["f_res_ghz"] * 1000, s["s11_min_db"]
        dmax = (s.get("farfield") or [{}])[0].get("Dmax_dBi")
        checks = [abs(f_mhz - num(rf["f_res_mhz"])) / num(rf["f_res_mhz"]) * 100 <= TOL_F_PCT,
                  abs(s11 - num(rf["s11_min_db"])) <= TOL_S11_DB]
        if num(rf["dmax_dbi"]) is not None and dmax is not None:
            checks.append(abs(dmax - num(rf["dmax_dbi"])) <= TOL_D_DB)
        ok = all(checks)
        ok_all &= ok
        dtxt = f"{dmax:6.2f}" if dmax is not None else "     -"
        print(f"{c:28} {f_mhz:12.1f} {num(rf['f_res_mhz']):9.1f} {s11:8.1f} {num(rf['s11_min_db']):7.1f} "
              f"{dtxt} {rf['dmax_dbi'] or '-':>6}  {'OK' if ok else 'REVISAR'}")
    print("\nResultado:", "todo dentro de tolerancia" if ok_all else "hay casos para revisar")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
