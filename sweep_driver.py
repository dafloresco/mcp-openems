# -*- coding: utf-8 -*-
"""
Barrido de un parámetro: ejecuta simulate.py una vez por valor (--set NOMBRE=VALOR --tag ...)
y reúne los resúmenes en results/sweep_<NOMBRE>.csv.

Uso: python sweep_driver.py <simulate.py> <NOMBRE> '[v1, v2, ...]' [--no-ff]
"""
import json
import subprocess
import sys
from pathlib import Path


def main():
    script, name, values = Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
    no_ff = "--no-ff" in sys.argv[4:]
    proj = script.parent
    rows = []
    for i, v in enumerate(values, 1):
        tag = f"sweep_{name}_{v:g}".replace(".", "p").replace("-", "m")
        print(f"=== [{i}/{len(values)}] {name} = {v:g}  (tag {tag}) ===", flush=True)
        cmd = [sys.executable, "-u", str(script), "--set", f"{name}={v}", "--tag", tag]
        if no_ff:
            cmd.append("--no-ff")
        r = subprocess.run(cmd, cwd=str(proj), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            if "Timestep:" in line or line.startswith(("RESUMEN_JSON:", "MALLA_JSON:", "RunFDTD", "Traceback", "AVISO")):
                print(line, flush=True)
        summary = proj / "results" / tag / "summary.json"
        if r.returncode != 0 or not summary.exists():
            print(f"FALLÓ {name}={v}: código {r.returncode}", flush=True)
            print(r.stdout[-2000:], flush=True)
            rows.append({name: v, "error": True})
            continue
        s = json.loads(summary.read_text(encoding="utf-8"))
        bw = s.get("bw_10db") or {}
        ff = (s.get("farfield") or [{}])[0]
        rows.append({name: v, "f_res_ghz": s["f_res_ghz"], "s11_min_db": s["s11_min_db"],
                     "bw_mhz": bw.get("bw_mhz"), "zin_re": s["zin_at_fres_ohm"][0], "zin_im": s["zin_at_fres_ohm"][1],
                     "realized_gain_dbi": ff.get("realized_gain_dBi")})
    out = proj / "results" / f"sweep_{name}.csv"
    out.parent.mkdir(exist_ok=True)
    cols = [name, "f_res_ghz", "s11_min_db", "bw_mhz", "zin_re", "zin_im", "realized_gain_dbi"]

    def cell(x):
        return "" if x is None else (f"{x:.6g}" if isinstance(x, float) else str(x))

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join("ERROR" if r.get("error") and c != name else cell(r.get(c)) for c in cols) + "\n")
    print("BARRIDO_JSON:" + json.dumps({"csv": str(out), "rows": rows}), flush=True)
    if any(r.get("error") for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
