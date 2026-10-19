# -*- coding: utf-8 -*-
"""
PLANTILLA DEL ESTUDIANTE (modo tutor): Parche rectangular alimentado por sonda sobre FR-4
Curso de Antenas - UNP. Script de simulación openEMS (método FDTD).

Especificación de la tarea:
  - Frecuencia objetivo: la asignada (2,30-2,60 GHz).
  - Sustrato FR-4: eps_r = 4,3; tan_d = 0,02; espesor h = 1,6 mm (ya definidos).
  - Resonancia a +/-1 % de la frecuencia objetivo y S11 <= -15 dB (50 ohm).
  - Entrega: este script, results/ y un informe de 1 página (S11, Zin, patrón, eficiencia).

Qué completar: los bloques marcados TODO 1, TODO 2 y TODO 3.
No cambies la CONFIGURACIÓN DE REFERENCIA ni el post-proceso: todos simulan
en las mismas condiciones y los resultados se guardan igual (results/).

Ejecución: doble clic en ejecutar.bat, o pídele al asistente que lo ejecute.
    ejecutar.bat --dry   construye el modelo y la malla sin simular (segundos)
Todas las dimensiones están en milímetros.
"""
import os, sys, json, argparse, time
import numpy as np
from numpy import pi, sqrt, sin, cos, tan
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0, EPS0

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description="Plantilla: Parche rectangular alimentado por sonda sobre FR-4")
ap.add_argument("--dry", action="store_true", help="solo modelo y malla, sin simular")
ap.add_argument("--post-only", action="store_true", help="solo post-proceso")
ap.add_argument("--no-ff", action="store_true", help="omitir el campo lejano")
ap.add_argument("--set", action="append", default=[], metavar="NOMBRE=VALOR")
ap.add_argument("--tag", default="", help="subcarpeta para esta corrida")
ap.add_argument("--ff-freq", type=float, action="append", default=[], help="GHz")
args = ap.parse_args()
t0 = time.time()

# ============================================================
# 1. PARÁMETROS (mm)
# ============================================================
# TODO 1: escribe tu frecuencia asignada (MHz) en 'f_obj_mhz' y agrega tus
# parámetros de diseño al diccionario, por ejemplo  'A': 12.5,  'B': 3.0
# Cada parámetro se convierte en una variable con su nombre (A, B, ...).
# No uses nombres que ya existen en el script (f, mesh, ports, ...).
params = {'f_obj_mhz': 0.0, 'h': 1.6, 'eps_r': 4.3, 'tan_d': 0.02}
for item in args.set:
    k, v = item.split("=", 1)
    if k not in params:
        sys.exit(f"Parámetro desconocido: {k}")
    params[k] = float(v)
globals().update(params)  # crea una variable por parámetro
if f_obj_mhz <= 0:
    sys.exit("TODO 1: escribe tu frecuencia asignada en params['f_obj_mhz'].")

# ============================================================
# 2. CONFIGURACIÓN DE REFERENCIA (no cambiar)
# ============================================================
unit = 1e-3  # metros por unidad de dibujo (mm)
f_min = 0.6 * f_obj_mhz * 1e6  # rango simulado: 0,6 a 1,4 veces la frecuencia objetivo
f_max = 1.4 * f_obj_mhz * 1e6
f0 = (f_min + f_max) / 2  # centro del pulso gaussiano
fc = (f_max - f_min) / 2  # semiancho del pulso (-20 dB)
# Se detiene cuando la energía cae -40 dB o tras 30000 pasos
FDTD = openEMS(NrTS=30000, EndCriteria=0.0001)
FDTD.SetGaussExcite(f0, fc)
BC = ['PML_8'] * 6  # contornos absorbentes: xmin, xmax, ymin, ymax, zmin, zmax
FDTD.SetBoundaryCond(BC)
CSX = ContinuousStructure()
FDTD.SetCSX(CSX)
mesh = CSX.GetGrid()
mesh.SetDeltaUnit(unit)
mesh_res = C0 / f_max / unit / 20.0  # celda máxima = lambda_min / 20
smooth_ratio = 1.4
thin_cells = 4  # celdas en capas delgadas (sustrato)

# ============================================================
# 3. MATERIALES (dados)
# ============================================================
mat = {}
# sustrato FR-4 (datos de la especificación). Las pérdidas se modelan con una
# conductividad equivalente kappa = 2*pi*f*eps0*eps_r*tan_d evaluada en f_obj
mat['sustrato'] = CSX.AddMaterial('sustrato', epsilon=eps_r, kappa=2*pi*f_obj_mhz*1e6*EPS0*eps_r*tan_d)
# pec: conductor eléctrico perfecto (PEC)
mat['pec'] = CSX.AddMetal('pec')

# ============================================================
# 4. GEOMETRÍA
# ============================================================
prims, metal_prims, diel_prims, thin_boxes = {}, [], [], []
bb_min = np.array([np.inf] * 3)
bb_max = -bb_min
def extend(start, stop, pad=0.0):
    """Actualiza la caja que envuelve toda la geometría."""
    global bb_min, bb_max
    pts = np.array([start, stop], dtype=float)
    bb_min = np.minimum(bb_min, pts.min(axis=0) - pad)
    bb_max = np.maximum(bb_max, pts.max(axis=0) + pad)
def extend_poly(xs, ys, n, elev, length):
    a1, a2 = (n + 1) % 3, (n + 2) % 3
    lo, hi = np.zeros(3), np.zeros(3)
    lo[a1], hi[a1] = min(xs), max(xs)
    lo[a2], hi[a2] = min(ys), max(ys)
    lo[n], hi[n] = min(elev, elev + length), max(elev, elev + length)
    extend(lo, hi)

# ------------------------------------------------------------
# TODO 2: agrega aquí cada pieza de tu antena. Cada pieza lleva tres líneas:
# crearla, actualizar la caja envolvente (extend) y registrarla para la malla.
# Sintaxis con ejemplos genéricos (NO son tu antena):
#
#   # lámina metálica de 10 x 20 mm en el plano z = 3
#   prims['lamina'] = mat['pec'].AddBox([-5, -10, 3], [5, 10, 3], priority=10)
#   extend([-5, -10, 3], [5, 10, 3])
#   metal_prims.append(prims['lamina'])
#
#   # bloque dieléctrico de 30 x 30 x 2 mm apoyado en z = 0
#   prims['bloque'] = mat['sustrato'].AddBox([-15, -15, 0], [15, 15, 2], priority=0)
#   extend([-15, -15, 0], [15, 15, 2])
#   thin_boxes.append(([-15, -15, 0], [15, 15, 2]))
#   diel_prims.append(prims['bloque'])
#
# Usa tus parámetros en las coordenadas, por ejemplo [0, 0, A/2].
# 'priority': gana el número mayor donde dos piezas se solapan (metal 10, dieléctrico 0).
# ------------------------------------------------------------
# >>> GEOMETRÍA

# ============================================================
# 5. PUERTOS
# ============================================================
ports = []
# ------------------------------------------------------------
# TODO 3: define el puerto de alimentación (50 ohm). Debe unir dos conductores.
# Ejemplo genérico: puerto 1 entre z = 0 y z = 2 en el punto (x, y) = (3, 0)
#   ports.append(FDTD.AddLumpedPort(1, 50.0, [3, 0, 0], [3, 0, 2], 'z', 1.0, priority=5, edges2grid='xy'))
#   extend([3, 0, 0], [3, 0, 2])
#   mesh.AddLine('z', [0, 2])
# El argumento 1.0 indica que este puerto es el que excita la antena.
# ------------------------------------------------------------
# >>> PUERTO
excited = 0
if not metal_prims:
    sys.exit("Falta la geometría: completa el TODO 2 de la sección 4.")
if not ports:
    sys.exit("Falta el puerto: completa el TODO 3 de la sección 5.")

# ============================================================
# 6. MALLA
# ============================================================
air = C0 / f_min / unit / 4  # margen de aire = lambda(f_min)/4 (referencia) en cada lado
# Una cara PEC o PMC es un plano de tierra o de simetría: la geometría llega hasta ella, sin aire
for i, ax in enumerate('xyz'):
    lo = bb_min[i] - (0 if BC[2 * i] in ('PEC', 'PMC') else air)
    hi = bb_max[i] + (0 if BC[2 * i + 1] in ('PEC', 'PMC') else air)
    mesh.AddLine(ax, [lo, hi])
# Bordes de metales: regla 1/3-2/3 para captar bien las corrientes de borde
if metal_prims:
    FDTD.AddEdges2Grid(dirs='xy', primitives=metal_prims, metal_edge_res=mesh_res / 2)
    FDTD.AddEdges2Grid(dirs='z', primitives=metal_prims)
if diel_prims:
    FDTD.AddEdges2Grid(dirs='all', primitives=diel_prims)
# Capas delgadas (p. ej. el sustrato) se subdividen en 'thin_cells' celdas
for start, stop in thin_boxes:
    for i, ax in enumerate('xyz'):
        lo, hi = sorted((start[i], stop[i]))
        if 0 < hi - lo < mesh_res:
            mesh.AddLine(ax, np.linspace(lo, hi, thin_cells + 1))
mesh.SmoothMeshLines('all', mesh_res, smooth_ratio)
nf2ff = FDTD.CreateNF2FFBox()  # caja para transformar campo cercano en lejano
FF_FREQS = []  # GHz; vacío = frecuencia de resonancia
THETA_STEP = 2.0

# ============================================================
# 7. SIMULACIÓN
# ============================================================
sim_path = os.path.join(HERE, 'sim', args.tag or 'base')
res_dir = os.path.join(HERE, 'results', args.tag) if args.tag else os.path.join(HERE, 'results')
os.makedirs(sim_path, exist_ok=True)
os.makedirs(res_dir, exist_ok=True)
CSX.Write2XML(os.path.join(res_dir, 'model.xml'))  # se abre con AppCSXCAD
lines = [np.array(mesh.GetLines(ax)) for ax in 'xyz']
d = [np.diff(l) for l in lines]
info = {
    'lines': [len(l) for l in lines],
    'cells': int(np.prod([len(l) - 1 for l in lines])),
    'min_cell_mm': [float(x.min()) for x in d],
    'max_cell_mm': [float(x.max()) for x in d],
    'mesh_res_mm': float(mesh_res),
    'air_margin_mm': float(air),
    'sim_box_mm': [[float(l[0]), float(l[-1])] for l in lines],
    'dt_courant_s': float(1 / (C0 * np.sqrt(sum(1 / (x.min() * unit) ** 2 for x in d)))),
    'params': params,
}
with open(os.path.join(res_dir, 'mesh_info.json'), 'w', encoding='utf-8') as fh:
    json.dump(info, fh, indent=2)
print('MALLA_JSON:' + json.dumps(info), flush=True)
if args.dry:
    sys.exit(0)
if not args.post_only:
    FDTD.Run(sim_path, cleanup=True)

# ============================================================
# 8. POST-PROCESO
# ============================================================
f = np.linspace(f_min, f_max, 1001)
for port in ports:
    port.CalcPort(sim_path, f)
port = ports[excited]
s11 = port.uf_ref / port.uf_inc
s11_dB = 20 * np.log10(np.abs(s11))
Zin = port.uf_tot / port.if_tot
np.savetxt(os.path.join(res_dir, 's11.csv'),
           np.column_stack([f / 1e9, s11_dB, s11.real, s11.imag, Zin.real, Zin.imag]),
           delimiter=',', fmt='%.6g', header='f_GHz,S11_dB,S11_re,S11_im,Zin_re,Zin_im', comments='')
if len(ports) == 1:
    with open(os.path.join(res_dir, 's11.s1p'), 'w') as fh:
        fh.write(f'! openEMS {os.path.basename(HERE)}\n# GHz S RI R {port.Z_ref}\n')
        for fi, si in zip(f, s11):
            fh.write(f'{fi/1e9:.6f} {si.real:.6e} {si.imag:.6e}\n')
else:
    cols, hdr = [f / 1e9], ['f_GHz']
    for k, pk in enumerate(ports):
        sk = pk.uf_ref / port.uf_inc
        cols.append(20 * np.log10(np.abs(sk)))
        hdr.append(f'S{k+1}{excited+1}_dB')
    np.savetxt(os.path.join(res_dir, 's_params.csv'), np.column_stack(cols), fmt='%.6g',
               delimiter=',', header=','.join(hdr), comments='')

idx = int(np.argmin(s11_dB))
summary = {
    'project': os.path.basename(HERE), 'tag': args.tag, 'params': params,
    'f_res_ghz': float(f[idx] / 1e9), 's11_min_db': float(s11_dB[idx]),
    'zin_at_fres_ohm': [float(Zin[idx].real), float(Zin[idx].imag)],
    'bw_10db': None, 'farfield': [], 'cells': info['cells'],
}
if s11_dB[idx] < -10:
    lo = idx
    while lo > 0 and s11_dB[lo - 1] < -10:
        lo -= 1
    hi = idx
    while hi < len(f) - 1 and s11_dB[hi + 1] < -10:
        hi += 1
    summary['bw_10db'] = {
        'f_low_ghz': float(f[lo] / 1e9), 'f_high_ghz': float(f[hi] / 1e9),
        'bw_mhz': float((f[hi] - f[lo]) / 1e6),
        'fbw_pct': float(100 * (f[hi] - f[lo]) / f[idx]),
        'touches_band_edge': bool(lo == 0 or hi == len(f) - 1)}

fig, axis = plt.subplots(tight_layout=True)
axis.plot(f / 1e9, s11_dB, 'k-', lw=2, label='S11')
axis.axhline(-10, color='r', ls=':', lw=1)
axis.set_xlabel('Frecuencia (GHz)'); axis.set_ylabel('S11 (dB)')
axis.set_title(f'Adaptación de entrada - mínimo {s11_dB[idx]:.1f} dB a {f[idx]/1e9:.3f} GHz')
axis.grid(); axis.legend()
fig.savefig(os.path.join(res_dir, 's11.png'), dpi=120); plt.close(fig)
fig, axis = plt.subplots(tight_layout=True)
axis.plot(f / 1e9, Zin.real, 'k-', lw=2, label='Re{Zin}')
axis.plot(f / 1e9, Zin.imag, 'r--', lw=2, label='Im{Zin}')
axis.set_xlabel('Frecuencia (GHz)'); axis.set_ylabel('Zin (ohm)'); axis.grid(); axis.legend()
fig.savefig(os.path.join(res_dir, 'zin.png'), dpi=120); plt.close(fig)

if nf2ff is not None and not args.no_ff:
    ff_freqs = [x * 1e9 for x in (args.ff_freq or FF_FREQS)] or [float(f[idx])]
    if not (args.ff_freq or FF_FREQS) and s11_dB[idx] > -10:
        print('AVISO: sin resonancia bajo -10 dB; el campo lejano se calcula igual en el mínimo de S11')
    theta = np.arange(-180.0, 180.0 + 1e-9, THETA_STEP)
    phi = [0.0, 90.0]
    ff = nf2ff.CalcNF2FF(sim_path, ff_freqs, theta, phi,
                         center=(bb_min + bb_max) / 2 * unit, read_cached=False)
    for i, fi in enumerate(ff_freqs):
        Dmax = float(np.ravel(ff.Dmax)[i]); Prad = float(np.ravel(ff.Prad)[i])
        P_acc = float(np.interp(fi, f, port.P_acc)); P_inc = float(np.interp(fi, f, port.P_inc))
        eff = Prad / P_acc if P_acc > 0 else float('nan')
        E = np.abs(ff.E_norm[i])
        D_dB = 20 * np.log10(E / E.max()) + 10 * np.log10(Dmax)
        tag_f = f'{fi/1e9:.4g}GHz'
        np.savetxt(os.path.join(res_dir, f'farfield_{tag_f}.csv'),
                   np.column_stack([theta, D_dB[:, 0], D_dB[:, 1]]), delimiter=',', fmt='%.6g',
                   header='theta_deg,D_phi0_dBi,D_phi90_dBi', comments='')
        fig, axis = plt.subplots(tight_layout=True)
        axis.plot(theta, D_dB[:, 0], 'k-', lw=2, label='phi=0 (plano xz)')
        axis.plot(theta, D_dB[:, 1], 'r--', lw=2, label='phi=90 (plano yz)')
        axis.set_ylim(10 * np.log10(Dmax) - 40, 10 * np.log10(Dmax) + 3)
        axis.set_xlabel('theta (grados)'); axis.set_ylabel('Directividad (dBi)')
        axis.set_title(f'Patrón a {fi/1e9:.4g} GHz'); axis.grid(); axis.legend()
        fig.savefig(os.path.join(res_dir, f'pattern_{tag_f}.png'), dpi=120); plt.close(fig)
        summary['farfield'].append({
            'f_ghz': fi / 1e9, 'Dmax_dBi': 10 * np.log10(Dmax),
            'rad_efficiency_pct': 100 * eff,
            'gain_dBi': 10 * np.log10(Dmax * eff) if eff > 0 else None,
            'realized_gain_dBi': 10 * np.log10(Dmax * Prad / P_inc) if P_inc > 0 else None,
            'Prad_W': Prad, 'Pacc_W': P_acc})

summary['elapsed_s'] = round(time.time() - t0, 1)
with open(os.path.join(res_dir, 'summary.json'), 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, indent=2)
print('RESUMEN_JSON:' + json.dumps(summary), flush=True)
