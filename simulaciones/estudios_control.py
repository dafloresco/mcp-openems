# -*- coding: utf-8 -*-
"""
Estudios de control de la prueba técnica (tablas 7 y 8 del artículo):

  convergencia  dipolo 915 MHz (L = 150,7 mm, PML) con mallas lambda/20, 40, 80, 120 y 160;
                parche FR-4 ajustado (PML) con mallas lambda/20, 30 y 40
  repeticion    tres corridas idénticas del dipolo (lambda/80) y del parche ajustado (lambda/20)
  contornos     misma geometría con MUR y con PML (parche del libro y parche ajustado)
  perdidas      parche ajustado con tan_d = 0,02 y con tan_d = 0,0027 (resto idéntico)
  hilo_finito   dipolo con conductor de sección cuadrada de 1 x 1 mm, mallas lambda/20, 40 y 80

Cada corrida se hace en una copia del script de referencia con una sola modificación, y registra
frecuencia de resonancia, S11, directividad, eficiencia, celdas, pasos de tiempo, duración y
memoria máxima (RSS). Salida: estudios_control.csv

    python estudios_control.py                 # todos (unos 45 min en el equipo de ENTORNO.md)
    python estudios_control.py convergencia    # solo un grupo
    python estudios_control.py dipolo_MUR      # solo un caso
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
RUNS = HERE / "_estudios"
DIP, PAT_ADJ, PAT_BOOK = "dipolo_915", "parche_fr4_2450_ajustado", "parche_fr4_2450_libro"


def case(group, name, base, mesh=None, bc=None, sets=(), wire=None):
    return dict(group=group, name=name, base=base, mesh=mesh, bc=bc, sets=list(sets), wire=wire)


CASES = (
    [case("convergencia", f"dipolo_malla{d}", DIP, mesh=d) for d in (20, 40, 80, 120, 160)]
    + [case("convergencia", f"parche_malla{d}", PAT_ADJ, mesh=d) for d in (20, 30, 40)]
    + [case("repeticion", f"dipolo_rep{i}", DIP) for i in (1, 2, 3)]
    + [case("repeticion", f"parche_rep{i}", PAT_ADJ) for i in (1, 2, 3)]
    + [case("contornos", "parche_libro_MUR", PAT_BOOK, bc="MUR"),
       case("contornos", "parche_libro_PML", PAT_BOOK, bc="PML_8"),
       case("contornos", "parche_ajustado_MUR", PAT_ADJ, bc="MUR"),
       case("contornos", "parche_ajustado_PML", PAT_ADJ, bc="PML_8"),
       case("contornos", "dipolo_MUR", DIP, bc="MUR")]  # su par PML es dipolo_malla80 (misma geometría y malla)
    + [case("perdidas", "parche_tand_0.02", PAT_ADJ),
       case("perdidas", "parche_tand_0.0027", PAT_ADJ, sets=["tan_d=0.0027"])]
    # Dipolo de sección finita (conductor cuadrado de 1 x 1 mm): geometría bien definida, a diferencia del hilo
    # de radio nulo cuyo radio efectivo depende de la celda. Sirve para mostrar convergencia de malla.
    + [case("hilo_finito", f"dipolo_seccion1mm_malla{d}", DIP, mesh=d, wire=0.5) for d in (20, 40, 80)]
)


def prepare(c) -> Path:
    d = RUNS / c["name"]
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    code = (HERE / c["base"] / "simulate.py").read_text(encoding="utf-8")
    if c["mesh"]:
        code, n = re.subn(r"(mesh_res = C0 / f_max / unit / )[\d.]+", rf"\g<1>{float(c['mesh'])}", code)
        assert n == 1, "no encontré la línea de malla"
    if c["bc"]:
        code, n = re.subn(r"^BC = .*$", f"BC = ['{c['bc']}'] * 6  # contornos (estudio de control)", code, flags=re.M)
        assert n == 1, "no encontré la línea BC"
    if c["wire"]:
        a = c["wire"]  # semilado del conductor (mm)
        code = code.replace("params = {", f"params = {{'a': {a}, ", 1)
        code = code.replace("g = params['g']\n", "g = params['g']\na = params['a']  # semilado del conductor\n", 1)
        n0 = code.count("[0.0, 0.0, ")
        code = code.replace("AddBox([0.0, 0.0, (g/2)], [0.0, 0.0, (L/2)]", "AddBox([-a, -a, (g/2)], [a, a, (L/2)]")
        code = code.replace("AddBox([0.0, 0.0, (-L/2)], [0.0, 0.0, (-g/2)]", "AddBox([-a, -a, (-L/2)], [a, a, (-g/2)]")
        code = code.replace("extend([0.0, 0.0, (g/2)], [0.0, 0.0, (L/2)])", "extend([-a, -a, (g/2)], [a, a, (L/2)])")
        code = code.replace("extend([0.0, 0.0, (-L/2)], [0.0, 0.0, (-g/2)])", "extend([-a, -a, (-L/2)], [a, a, (-g/2)])")
        code = code.replace("AddLumpedPort(1, 50.0, [0.0, 0.0, (-g/2)], [0.0, 0.0, (g/2)]",
                            "AddLumpedPort(1, 50.0, [-a, -a, (-g/2)], [a, a, (g/2)]")
        assert code.count("[0.0, 0.0, ") < n0, "no se aplicó la sección finita"
    (d / "simulate.py").write_text(code, encoding="utf-8")
    return d


def run(c) -> dict:
    d = prepare(c)
    cmd = [sys.executable, "simulate.py"] + [a for s in c["sets"] for a in ("--set", s)]
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    peak = [0]

    def watch():
        try:
            p = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    rss = p.memory_info().rss + sum(ch.memory_info().rss for ch in p.children(recursive=True))
                    peak[0] = max(peak[0], rss)
                except psutil.Error:
                    pass
                time.sleep(0.5)
        except psutil.Error:
            pass

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    out, _ = proc.communicate()
    th.join(timeout=2)
    elapsed = time.time() - t0
    (d / "simulacion.log").write_text(out, encoding="utf-8")
    row = dict(grupo=c["group"], caso=c["name"], base=c["base"], malla=c["mesh"] or "", contorno=c["bc"] or "",
               cambios=";".join(c["sets"]), ok=proc.returncode == 0, duracion_s=round(elapsed, 1),
               memoria_max_mb=round(peak[0] / 2**20))
    m = re.findall(r"end-criteria of .*? reached after (\d+) timesteps \(([-\d.]+)dB\)", out)
    mx = re.findall(r"max\. number of timesteps", out, flags=re.I)
    row["pasos"] = int(m[-1][0]) if m else ""
    row["parada"] = f"criterio de energía ({m[-1][1]} dB)" if m else ("máximo de pasos" if mx else "")
    if proc.returncode == 0:
        s = json.loads((d / "results" / "summary.json").read_text(encoding="utf-8"))
        ff = (s.get("farfield") or [{}])[0]
        bw = s.get("bw_10db") or {}
        row.update(f_res_mhz=round(s["f_res_ghz"] * 1000, 2), s11_min_db=round(s["s11_min_db"], 2),
                   zin_re=round(s["zin_at_fres_ohm"][0], 2), zin_im=round(s["zin_at_fres_ohm"][1], 2),
                   bw_mhz=round(bw.get("bw_mhz", 0), 1) if bw else "", dmax_dbi=round(ff.get("Dmax_dBi", 0), 3) if ff else "",
                   eficiencia_pct=round(ff.get("rad_efficiency_pct", 0), 2) if ff else "", celdas=s.get("cells", ""))
    return row


def main():
    sel = sys.argv[1:]  # grupos o nombres de caso
    todo = [c for c in CASES if not sel or c["group"] in sel or c["name"] in sel]
    out = HERE / "estudios_control.csv"
    fields = ["grupo", "caso", "base", "malla", "contorno", "cambios", "ok", "f_res_mhz", "s11_min_db", "zin_re",
              "zin_im", "bw_mhz", "dmax_dbi", "eficiencia_pct", "celdas", "pasos", "parada", "duracion_s", "memoria_max_mb"]
    new = not out.exists()
    with open(out, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        for i, c in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {c['name']} ...", flush=True)
            r = run(c)
            w.writerow(r)
            fh.flush()
            print("   ", {k: r.get(k) for k in ("f_res_mhz", "s11_min_db", "dmax_dbi", "celdas", "duracion_s", "memoria_max_mb")}, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
