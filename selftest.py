# -*- coding: utf-8 -*-
"""
Prueba de extremo a extremo del servidor (sin cliente MCP): crea un parche de 2.45 GHz,
revisa la malla, simula y lee resultados. Usa el proyecto _selftest_parche del workspace.

    .venv\\Scripts\\python.exe selftest.py           (completo, ~2-5 min)
    .venv\\Scripts\\python.exe selftest.py --quick   (sin simular)
"""
import shutil
import sys

import server as s

quick = "--quick" in sys.argv
name = "_selftest_parche"
shutil.rmtree(s.oems.workspace / name, ignore_errors=True)

steps = [
    ("status", lambda: s.oems_status()),
    ("new", lambda: s.oems_new_project(name)),
    ("calc", lambda: s.oems_patch_calculator(2.45, 4.3, 1.6)),
    ("template", lambda: s.oems_create_microstrip_patch_template(freq_ghz=2.45, eps_r=4.3, tan_d=0.02, h_mm=1.6)),
    ("bad_expr", lambda: s.oems_add_box("x", "pec", ["-Q/2", 0, 0], [1, 1, 1])),
    ("polygon", lambda: s.oems_add_polygon("tri", "pec", [[0, 0], [5, 0], [0, 5]], "x", "h", 0.0)),
    ("del_polygon", lambda: s.oems_delete_primitive("tri")),
    ("setup", lambda: s.oems_query_setup()),
    ("check", lambda: s.oems_design_check()),
    ("script", lambda: s.oems_generate_script()),
    ("mesh", lambda: s.oems_preview_mesh()),
]
if not quick:
    steps += [
        ("run", lambda: s.oems_run_simulation(wait=True, max_wait_s=900)),
        ("results", lambda: s.oems_get_results()),
        ("csv", lambda: s.oems_read_result_csv(f"{name}/results/s11.csv", 12)),
        ("report", lambda: s.oems_generate_markdown_report("Selftest parche 2.45 GHz")),
    ]

failed = 0
for label, fn in steps:
    out = fn()
    bad = out.startswith("Error") and label != "bad_expr"
    if label == "bad_expr" and not out.startswith("Error"):
        bad = True
    failed += bad
    print(f"\n===== {label} {'FAIL' if bad else 'ok'} =====\n{out}")
print(f"\nRESULTADO: {len(steps) - failed}/{len(steps)} pasos ok")
sys.exit(1 if failed else 0)
