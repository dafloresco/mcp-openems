# -*- coding: utf-8 -*-
"""
Generador del script de simulación openEMS (simulate.py) a partir de model.json.

El script generado es autocontenido y legible: parámetros como variables Python,
geometría con expresiones (p. ej. -L/2) y un post-proceso que escribe CSV, PNG y
summary.json. Así el estudiante puede ver exactamente qué hizo el agente.
"""
from datetime import datetime

AXES = "xyz"

# Nombres que usa el script generado; un parámetro no puede llamarse así.
RESERVED_NAMES = {
    "np", "plt", "os", "sys", "json", "argparse", "matplotlib", "pi", "sqrt", "sin",
    "cos", "tan", "C0", "EPS0", "HERE", "ap", "args", "params", "unit", "f_min", "f_max",
    "f0", "fc", "FDTD", "CSX", "mesh", "mesh_res", "mat", "prims", "ports", "bb_min",
    "bb_max", "extend", "air", "sim_path", "res_dir", "f", "port", "s11", "s11_dB", "Zin",
    "k", "v", "item", "nf2ff", "ContinuousStructure", "openEMS", "metal_prims",
    "diel_prims", "thin_boxes", "summary", "info", "lines", "ax", "i", "fig", "axis",
    "theta", "phi", "ff", "ff_freqs", "idx", "FF_FREQS", "THETA_STEP", "excited",
    "smooth_ratio", "thin_cells", "start", "stop", "d", "lo", "hi", "t0", "data",
    "print", "range", "len", "float", "int", "str", "abs", "min", "max", "list", "dict",
    "True", "False", "None", "open", "round", "sum", "zip", "enumerate", "pts", "a1",
    "a2", "fh", "cols", "hdr", "pk", "sk", "si", "fi", "E", "D_dB", "Dmax", "Prad",
    "P_acc", "P_inc", "eff", "tag_f", "extend_poly", "time", "l", "x", "n", "elev",
    "length", "xs", "ys", "global", "pad", "BC",
}


def fmt(value) -> str:
    """Número -> literal Python; expresión -> entre paréntesis (o nombre solo)."""
    if isinstance(value, (int, float)):
        return repr(float(value))
    s = str(value).strip()
    if s.isidentifier():
        return s
    return f"({s})"


def vec(values) -> str:
    return "[" + ", ".join(fmt(v) for v in values) + "]"


def _material_lines(name: str, m: dict) -> list[str]:
    t = m["type"]
    if t == "dielectric":
        eps = fmt(m["eps_r"])
        tan_d = fmt(m.get("tan_d", 0.0))
        f_tan = fmt(m.get("tan_d_freq_ghz", 1.0))
        return [
            f"# {name}: dieléctrico, eps_r={m['eps_r']}, tan_d={m.get('tan_d', 0.0)} @ {m.get('tan_d_freq_ghz', 1.0)} GHz",
            f"# Las pérdidas se modelan con una conductividad equivalente kappa = 2*pi*f*eps0*eps_r*tan_d",
            f"mat[{name!r}] = CSX.AddMaterial({name!r}, epsilon={eps}, "
            f"kappa=2*pi*{f_tan}*1e9*EPS0*{eps}*{tan_d})",
        ]
    if t == "conducting_sheet":
        return [
            f"# {name}: lámina conductora (sigma={m['sigma']} S/m, espesor={m['thickness_um']} um)",
            f"mat[{name!r}] = CSX.AddConductingSheet({name!r}, conductivity={fmt(m['sigma'])}, "
            f"thickness={fmt(m['thickness_um'])}*1e-6)",
        ]
    return [
        f"# {name}: conductor eléctrico perfecto (PEC)",
        f"mat[{name!r}] = CSX.AddMetal({name!r})",
    ]


def _polygon_points(p: dict) -> tuple[str, str]:
    xs = "[" + ", ".join(fmt(pt[0]) for pt in p["points"]) + "]"
    ys = "[" + ", ".join(fmt(pt[1]) for pt in p["points"]) + "]"
    return xs, ys


def _primitive_lines(p: dict, materials: dict) -> list[str]:
    name, mname, kind = p["name"], p["material"], p["kind"]
    prio = int(p.get("priority", 10 if materials[mname]["type"] != "dielectric" else 0))
    is_metal = materials[mname]["type"] != "dielectric"
    group = "metal_prims" if is_metal else "diel_prims"
    out = [f"# {name}: {kind} de material '{mname}'"]
    if kind == "box":
        s, e = vec(p["start"]), vec(p["stop"])
        out.append(f"prims[{name!r}] = mat[{mname!r}].AddBox({s}, {e}, priority={prio})")
        out.append(f"extend({s}, {e})")
        if not is_metal:
            out.append(f"thin_boxes.append(({s}, {e}))")
    elif kind == "cylinder":
        s, e, r = vec(p["start"]), vec(p["stop"]), fmt(p["radius"])
        out.append(f"prims[{name!r}] = mat[{mname!r}].AddCylinder({s}, {e}, {r}, priority={prio})")
        out.append(f"extend({s}, {e}, pad={r})")
    elif kind == "polygon":
        xs, ys = _polygon_points(p)
        n = AXES.index(p["normal"])
        elev = fmt(p["elevation"])
        a1, a2 = (n + 1) % 3, (n + 2) % 3
        out.append(f"# puntos en el plano {AXES[a1]}{AXES[a2]}, normal {p['normal']}, elevación {p['elevation']}")
        if p.get("length") not in (None, 0, 0.0, "0"):
            ln = fmt(p["length"])
            out.append(f"prims[{name!r}] = mat[{mname!r}].AddLinPoly([{xs}, {ys}], {p['normal']!r}, {elev}, {ln}, priority={prio})")
            out.append(f"extend_poly({xs}, {ys}, {n}, {elev}, {ln})")
        else:
            out.append(f"prims[{name!r}] = mat[{mname!r}].AddPolygon([{xs}, {ys}], {p['normal']!r}, {elev}, priority={prio})")
            out.append(f"extend_poly({xs}, {ys}, {n}, {elev}, 0.0)")
    else:
        raise ValueError(f"Tipo de primitiva desconocido: {kind}")
    out.append(f"{group}.append(prims[{name!r}])")
    return out


def generate_script(model: dict) -> str:
    name = model["name"]
    freq = model.get("frequency") or {}
    fdtd = model.get("fdtd", {})
    meshcfg = model.get("mesh", {})
    bcs = model.get("boundaries", ["MUR"] * 6)
    nf = model.get("nf2ff", {"enabled": False})
    params = model.get("parameters", {})
    materials = model.get("materials", {})
    margin = model.get("air_margin_mm")

    L = []
    w = L.append
    w("# -*- coding: utf-8 -*-")
    w('"""')
    w(f"Proyecto openEMS: {name}")
    w(f"Generado por mcp-openems el {datetime.now():%Y-%m-%d %H:%M} a partir de model.json.")
    w("")
    w("Este script es autocontenido: puedes leerlo, modificarlo y ejecutarlo con")
    w("    python simulate.py              (simula y post-procesa)")
    w("    python simulate.py --dry        (solo construye el modelo y la malla)")
    w("    python simulate.py --post-only  (recalcula resultados sin volver a simular)")
    w("    python simulate.py --set L=29.5 --tag prueba   (cambia un parámetro)")
    w("Todas las dimensiones están en milímetros.")
    w('"""')
    w("import os, sys, json, argparse, time")
    w("import numpy as np")
    w("from numpy import pi, sqrt, sin, cos, tan")
    w("import matplotlib")
    w('matplotlib.use("Agg")')
    w("import matplotlib.pyplot as plt")
    w("from CSXCAD import ContinuousStructure")
    w("from openEMS import openEMS")
    w("from openEMS.physical_constants import C0, EPS0")
    w("")
    w("HERE = os.path.dirname(os.path.abspath(__file__))")
    w('ap = argparse.ArgumentParser(description="Simulación openEMS: ' + name + '")')
    w('ap.add_argument("--dry", action="store_true", help="solo modelo y malla, sin simular")')
    w('ap.add_argument("--post-only", action="store_true", help="solo post-proceso")')
    w('ap.add_argument("--no-ff", action="store_true", help="omitir el campo lejano")')
    w('ap.add_argument("--set", action="append", default=[], metavar="NOMBRE=VALOR")')
    w('ap.add_argument("--tag", default="", help="subcarpeta para esta corrida")')
    w('ap.add_argument("--ff-freq", type=float, action="append", default=[], help="GHz")')
    w("args = ap.parse_args()")
    w("t0 = time.time()")
    w("")
    w("# ============================================================")
    w("# 1. PARÁMETROS (mm)")
    w("# ============================================================")
    w("params = {" + ", ".join(f"{k!r}: {float(v)!r}" for k, v in params.items()) + "}")
    w("for item in args.set:")
    w('    k, v = item.split("=", 1)')
    w("    if k not in params:")
    w('        sys.exit(f"Parámetro desconocido: {k}")')
    w("    params[k] = float(v)")
    for k in params:
        w(f"{k} = params[{k!r}]")
    w("")
    w("# ============================================================")
    w("# 2. FRECUENCIA, EXCITACIÓN Y SOLVER FDTD")
    w("# ============================================================")
    w("unit = 1e-3  # metros por unidad de dibujo (mm)")
    w(f"f_min = {float(freq.get('fmin_ghz', 1.0))!r} * 1e9")
    w(f"f_max = {float(freq.get('fmax_ghz', 3.0))!r} * 1e9")
    w("f0 = (f_min + f_max) / 2  # centro del pulso gaussiano")
    w("fc = (f_max - f_min) / 2  # semiancho del pulso (-20 dB)")
    end_db = float(fdtd.get("end_criteria_db", -40.0))
    w(f"# Se detiene cuando la energía cae {end_db} dB o tras {int(fdtd.get('max_timesteps', 30000))} pasos")
    w(f"FDTD = openEMS(NrTS={int(fdtd.get('max_timesteps', 30000))}, EndCriteria={10 ** (end_db / 10)!r})")
    w("FDTD.SetGaussExcite(f0, fc)")
    w(f"BC = {bcs!r}  # contornos: xmin, xmax, ymin, ymax, zmin, zmax")
    w("FDTD.SetBoundaryCond(BC)")
    w("CSX = ContinuousStructure()")
    w("FDTD.SetCSX(CSX)")
    w("mesh = CSX.GetGrid()")
    w("mesh.SetDeltaUnit(unit)")
    div = float(meshcfg.get("divisor", 20))
    w(f"mesh_res = C0 / f_max / unit / {div!r}  # celda máxima = lambda_min / {div:g}")
    w(f"smooth_ratio = {float(meshcfg.get('smooth_ratio', 1.4))!r}")
    w(f"thin_cells = {int(meshcfg.get('thin_layer_cells', 4))}  # celdas en capas delgadas (sustrato)")
    w("")
    w("# ============================================================")
    w("# 3. MATERIALES")
    w("# ============================================================")
    w("mat = {}")
    for mname, m in materials.items():
        L.extend(_material_lines(mname, m))
    w("")
    w("# ============================================================")
    w("# 4. GEOMETRÍA")
    w("# ============================================================")
    w("prims, metal_prims, diel_prims, thin_boxes = {}, [], [], []")
    w("bb_min = np.array([np.inf] * 3)")
    w("bb_max = -bb_min")
    w("def extend(start, stop, pad=0.0):")
    w('    """Actualiza la caja que envuelve toda la geometría."""')
    w("    global bb_min, bb_max")
    w("    pts = np.array([start, stop], dtype=float)")
    w("    bb_min = np.minimum(bb_min, pts.min(axis=0) - pad)")
    w("    bb_max = np.maximum(bb_max, pts.max(axis=0) + pad)")
    w("def extend_poly(xs, ys, n, elev, length):")
    w("    a1, a2 = (n + 1) % 3, (n + 2) % 3")
    w("    lo, hi = np.zeros(3), np.zeros(3)")
    w("    lo[a1], hi[a1] = min(xs), max(xs)")
    w("    lo[a2], hi[a2] = min(ys), max(ys)")
    w("    lo[n], hi[n] = min(elev, elev + length), max(elev, elev + length)")
    w("    extend(lo, hi)")
    w("")
    for p in model.get("primitives", []):
        L.extend(_primitive_lines(p, materials))
        w("")
    w("# ============================================================")
    w("# 5. PUERTOS")
    w("# ============================================================")
    w("ports = []")
    excited = 0
    for i, pt in enumerate(model.get("ports", [])):
        if pt.get("excite") and not excited:
            excited = i
        exc = "1.0" if pt.get("excite") else "0"
        s, e = vec(pt["start"]), vec(pt["stop"])
        w(f"# Puerto {pt['number']}: concentrado, R={pt['resistance']} ohm, dirección {pt['direction']}"
          + (" (excitado)" if pt.get("excite") else ""))
        w(f"ports.append(FDTD.AddLumpedPort({int(pt['number'])}, {fmt(pt['resistance'])}, {s}, {e}, "
          f"{pt['direction']!r}, {exc}, priority=5, edges2grid='xy'))")
        w(f"extend({s}, {e})")
        d = AXES.index(pt["direction"])
        w(f"mesh.AddLine({pt['direction']!r}, [{fmt(pt['start'][d])}, {fmt(pt['stop'][d])}])")
    w(f"excited = {excited}")
    w("")
    w("# ============================================================")
    w("# 6. MALLA")
    w("# ============================================================")
    if margin in (None, 0, 0.0):
        w("air = C0 / f_min / unit / 4  # margen de aire = lambda(f_min)/4 en cada lado")
    else:
        w(f"air = {float(margin)!r}  # margen de aire fijado por el usuario (mm)")
    w("# Una cara PEC o PMC es un plano de tierra o de simetría: la geometría llega hasta ella, sin aire")
    w("for i, ax in enumerate('xyz'):")
    w("    lo = bb_min[i] - (0 if BC[2 * i] in ('PEC', 'PMC') else air)")
    w("    hi = bb_max[i] + (0 if BC[2 * i + 1] in ('PEC', 'PMC') else air)")
    w("    mesh.AddLine(ax, [lo, hi])")
    w("# Bordes de metales: regla 1/3-2/3 para captar bien las corrientes de borde")
    w("if metal_prims:")
    w("    FDTD.AddEdges2Grid(dirs='xy', primitives=metal_prims, metal_edge_res=mesh_res / 2)")
    w("    FDTD.AddEdges2Grid(dirs='z', primitives=metal_prims)")
    w("if diel_prims:")
    w("    FDTD.AddEdges2Grid(dirs='all', primitives=diel_prims)")
    w("# Capas delgadas (p. ej. el sustrato) se subdividen en 'thin_cells' celdas")
    w("for start, stop in thin_boxes:")
    w("    for i, ax in enumerate('xyz'):")
    w("        lo, hi = sorted((start[i], stop[i]))")
    w("        if 0 < hi - lo < mesh_res:")
    w("            mesh.AddLine(ax, np.linspace(lo, hi, thin_cells + 1))")
    w("mesh.SmoothMeshLines('all', mesh_res, smooth_ratio)")
    if nf.get("enabled"):
        w("nf2ff = FDTD.CreateNF2FFBox()  # caja para transformar campo cercano en lejano")
    else:
        w("nf2ff = None  # campo lejano desactivado")
    ff_freqs = [float(x) for x in nf.get("freqs_ghz", [])]
    w(f"FF_FREQS = {ff_freqs!r}  # GHz; vacío = frecuencia de resonancia")
    w(f"THETA_STEP = {float(nf.get('theta_step_deg', 2.0))!r}")
    w("")
    w("# ============================================================")
    w("# 7. SIMULACIÓN")
    w("# ============================================================")
    w("sim_path = os.path.join(HERE, 'sim', args.tag or 'base')")
    w("res_dir = os.path.join(HERE, 'results', args.tag) if args.tag else os.path.join(HERE, 'results')")
    w("os.makedirs(sim_path, exist_ok=True)")
    w("os.makedirs(res_dir, exist_ok=True)")
    w("CSX.Write2XML(os.path.join(res_dir, 'model.xml'))  # se abre con AppCSXCAD")
    w("lines = [np.array(mesh.GetLines(ax)) for ax in 'xyz']")
    w("d = [np.diff(l) for l in lines]")
    w("info = {")
    w("    'lines': [len(l) for l in lines],")
    w("    'cells': int(np.prod([len(l) - 1 for l in lines])),")
    w("    'min_cell_mm': [float(x.min()) for x in d],")
    w("    'max_cell_mm': [float(x.max()) for x in d],")
    w("    'mesh_res_mm': float(mesh_res),")
    w("    'air_margin_mm': float(air),")
    w("    'sim_box_mm': [[float(l[0]), float(l[-1])] for l in lines],")
    w("    'dt_courant_s': float(1 / (C0 * np.sqrt(sum(1 / (x.min() * unit) ** 2 for x in d)))),")
    w("    'params': params,")
    w("}")
    w("with open(os.path.join(res_dir, 'mesh_info.json'), 'w', encoding='utf-8') as fh:")
    w("    json.dump(info, fh, indent=2)")
    w("print('MALLA_JSON:' + json.dumps(info), flush=True)")
    w("if args.dry:")
    w("    sys.exit(0)")
    w("if not args.post_only:")
    w("    FDTD.Run(sim_path, cleanup=True)")
    w("")
    w("# ============================================================")
    w("# 8. POST-PROCESO")
    w("# ============================================================")
    w("f = np.linspace(f_min, f_max, 1001)")
    w("for port in ports:")
    w("    port.CalcPort(sim_path, f)")
    w("port = ports[excited]")
    w("s11 = port.uf_ref / port.uf_inc")
    w("s11_dB = 20 * np.log10(np.abs(s11))")
    w("Zin = port.uf_tot / port.if_tot")
    w("np.savetxt(os.path.join(res_dir, 's11.csv'),")
    w("           np.column_stack([f / 1e9, s11_dB, s11.real, s11.imag, Zin.real, Zin.imag]),")
    w("           delimiter=',', fmt='%.6g', header='f_GHz,S11_dB,S11_re,S11_im,Zin_re,Zin_im', comments='')")
    w("if len(ports) == 1:")
    w("    with open(os.path.join(res_dir, 's11.s1p'), 'w') as fh:")
    w("        fh.write(f'! openEMS {os.path.basename(HERE)}\\n# GHz S RI R {port.Z_ref}\\n')")
    w("        for fi, si in zip(f, s11):")
    w("            fh.write(f'{fi/1e9:.6f} {si.real:.6e} {si.imag:.6e}\\n')")
    w("else:")
    w("    cols, hdr = [f / 1e9], ['f_GHz']")
    w("    for k, pk in enumerate(ports):")
    w("        sk = pk.uf_ref / port.uf_inc")
    w("        cols.append(20 * np.log10(np.abs(sk)))")
    w("        hdr.append(f'S{k+1}{excited+1}_dB')")
    w("    np.savetxt(os.path.join(res_dir, 's_params.csv'), np.column_stack(cols), fmt='%.6g',")
    w("               delimiter=',', header=','.join(hdr), comments='')")
    w("")
    w("idx = int(np.argmin(s11_dB))")
    w("summary = {")
    w("    'project': os.path.basename(HERE), 'tag': args.tag, 'params': params,")
    w("    'f_res_ghz': float(f[idx] / 1e9), 's11_min_db': float(s11_dB[idx]),")
    w("    'zin_at_fres_ohm': [float(Zin[idx].real), float(Zin[idx].imag)],")
    w("    'bw_10db': None, 'farfield': [], 'cells': info['cells'],")
    w("}")
    w("if s11_dB[idx] < -10:")
    w("    lo = idx")
    w("    while lo > 0 and s11_dB[lo - 1] < -10:")
    w("        lo -= 1")
    w("    hi = idx")
    w("    while hi < len(f) - 1 and s11_dB[hi + 1] < -10:")
    w("        hi += 1")
    w("    summary['bw_10db'] = {")
    w("        'f_low_ghz': float(f[lo] / 1e9), 'f_high_ghz': float(f[hi] / 1e9),")
    w("        'bw_mhz': float((f[hi] - f[lo]) / 1e6),")
    w("        'fbw_pct': float(100 * (f[hi] - f[lo]) / f[idx]),")
    w("        'touches_band_edge': bool(lo == 0 or hi == len(f) - 1)}")
    w("")
    w("fig, axis = plt.subplots(tight_layout=True)")
    w("axis.plot(f / 1e9, s11_dB, 'k-', lw=2, label='S11')")
    w("axis.axhline(-10, color='r', ls=':', lw=1)")
    w("axis.set_xlabel('Frecuencia (GHz)'); axis.set_ylabel('S11 (dB)')")
    w("axis.set_title(f'Adaptación de entrada - mínimo {s11_dB[idx]:.1f} dB a {f[idx]/1e9:.3f} GHz')")
    w("axis.grid(); axis.legend()")
    w("fig.savefig(os.path.join(res_dir, 's11.png'), dpi=120); plt.close(fig)")
    w("fig, axis = plt.subplots(tight_layout=True)")
    w("axis.plot(f / 1e9, Zin.real, 'k-', lw=2, label='Re{Zin}')")
    w("axis.plot(f / 1e9, Zin.imag, 'r--', lw=2, label='Im{Zin}')")
    w("axis.set_xlabel('Frecuencia (GHz)'); axis.set_ylabel('Zin (ohm)'); axis.grid(); axis.legend()")
    w("fig.savefig(os.path.join(res_dir, 'zin.png'), dpi=120); plt.close(fig)")
    w("")
    w("if nf2ff is not None and not args.no_ff:")
    w("    ff_freqs = [x * 1e9 for x in (args.ff_freq or FF_FREQS)] or [float(f[idx])]")
    w("    if not (args.ff_freq or FF_FREQS) and s11_dB[idx] > -10:")
    w("        print('AVISO: sin resonancia bajo -10 dB; el campo lejano se calcula igual en el mínimo de S11')")
    w("    theta = np.arange(-180.0, 180.0 + 1e-9, THETA_STEP)")
    w("    phi = [0.0, 90.0]")
    w("    ff = nf2ff.CalcNF2FF(sim_path, ff_freqs, theta, phi,")
    w("                         center=(bb_min + bb_max) / 2 * unit, read_cached=False)")
    w("    for i, fi in enumerate(ff_freqs):")
    w("        Dmax = float(np.ravel(ff.Dmax)[i]); Prad = float(np.ravel(ff.Prad)[i])")
    w("        P_acc = float(np.interp(fi, f, port.P_acc)); P_inc = float(np.interp(fi, f, port.P_inc))")
    w("        eff = Prad / P_acc if P_acc > 0 else float('nan')")
    w("        E = np.abs(ff.E_norm[i])")
    w("        D_dB = 20 * np.log10(E / E.max()) + 10 * np.log10(Dmax)")
    w("        tag_f = f'{fi/1e9:.4g}GHz'")
    w("        np.savetxt(os.path.join(res_dir, f'farfield_{tag_f}.csv'),")
    w("                   np.column_stack([theta, D_dB[:, 0], D_dB[:, 1]]), delimiter=',', fmt='%.6g',")
    w("                   header='theta_deg,D_phi0_dBi,D_phi90_dBi', comments='')")
    w("        fig, axis = plt.subplots(tight_layout=True)")
    w("        axis.plot(theta, D_dB[:, 0], 'k-', lw=2, label='phi=0 (plano xz)')")
    w("        axis.plot(theta, D_dB[:, 1], 'r--', lw=2, label='phi=90 (plano yz)')")
    w("        axis.set_ylim(10 * np.log10(Dmax) - 40, 10 * np.log10(Dmax) + 3)")
    w("        axis.set_xlabel('theta (grados)'); axis.set_ylabel('Directividad (dBi)')")
    w("        axis.set_title(f'Patrón a {fi/1e9:.4g} GHz'); axis.grid(); axis.legend()")
    w("        fig.savefig(os.path.join(res_dir, f'pattern_{tag_f}.png'), dpi=120); plt.close(fig)")
    w("        summary['farfield'].append({")
    w("            'f_ghz': fi / 1e9, 'Dmax_dBi': 10 * np.log10(Dmax),")
    w("            'rad_efficiency_pct': 100 * eff,")
    w("            'gain_dBi': 10 * np.log10(Dmax * eff) if eff > 0 else None,")
    w("            'realized_gain_dBi': 10 * np.log10(Dmax * Prad / P_inc) if P_inc > 0 else None,")
    w("            'Prad_W': Prad, 'Pacc_W': P_acc})")
    w("")
    w("summary['elapsed_s'] = round(time.time() - t0, 1)")
    w("with open(os.path.join(res_dir, 'summary.json'), 'w', encoding='utf-8') as fh:")
    w("    json.dump(summary, fh, indent=2)")
    w("print('RESUMEN_JSON:' + json.dumps(summary), flush=True)")
    return "\n".join(L) + "\n"
