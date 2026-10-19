# -*- coding: utf-8 -*-
"""
Puente entre el servidor MCP y openEMS.

Diseño (análogo a mcp-cst-studio):
- Solo trabaja dentro de OPENEMS_WORKSPACE.
- Cada proyecto es una carpeta con model.json (modelo declarativo) y simulate.py
  (script openEMS generado, legible y ejecutable por el estudiante).
- Las simulaciones corren en un subproceso, para no bloquear el servidor MCP.
- El servidor nunca importa openEMS: todo el cálculo pesado ocurre en el subproceso.
"""
import ast
import ctypes
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from openems_scriptgen import AXES, RESERVED_NAMES, generate_script

C0 = 299792458.0
FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan}
CONSTS = {"pi": math.pi}
NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,80}$")
BC_OPTIONS = {"PEC", "PMC", "MUR", "PML_8"}


class ModelError(Exception):
    pass


# ============================================================
# EXPRESIONES SEGURAS
# ============================================================

def eval_expr(value: Any, params: dict) -> float:
    """Evalúa un número o una expresión con parámetros (+ - * / ** sqrt sin cos tan pi)."""
    if isinstance(value, bool):
        raise ModelError(f"Valor no numérico: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        tree = ast.parse(str(value), mode="eval")
    except SyntaxError as e:
        raise ModelError(f"Expresión inválida '{value}': {e.msg}")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in params:
                return float(params[node.id])
            if node.id in CONSTS:
                return CONSTS[node.id]
            raise ModelError(f"Parámetro no definido en '{value}': {node.id}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = ev(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
            return a ** b
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in FUNCS and len(node.args) == 1 and not node.keywords):
            return FUNCS[node.func.id](ev(node.args[0]))
        raise ModelError(f"Elemento no permitido en la expresión '{value}'")

    try:
        return ev(tree)
    except ZeroDivisionError:
        raise ModelError(f"División por cero en '{value}'")


def norm_value(value: Any) -> Any:
    """Normaliza la entrada del agente: '12.5' -> 12.5; 'L/2' se mantiene como expresión."""
    if isinstance(value, str):
        s = value.strip()
        try:
            return float(s)
        except ValueError:
            return s
    return float(value)


# ============================================================
# PROCESOS (Windows)
# ============================================================

def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class OpenEMSBridge:
    def __init__(self):
        self.workspace = Path(os.getenv("OPENEMS_WORKSPACE", r"C:\OPENEMS_MCP_WORK")).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.install_path = Path(os.getenv("CSXCAD_INSTALL_PATH", r"C:\openEMS-0.37.0"))
        self.python = sys.executable
        self.project: Path | None = None
        self._proc: subprocess.Popen | None = None

    # ------------------------------------------------------------
    # utilidades internas
    # ------------------------------------------------------------
    def _safe_path(self, file_name: str) -> Path:
        candidate = Path(file_name)
        path = candidate.resolve() if candidate.is_absolute() else (self.workspace / candidate).resolve()
        if not str(path).lower().startswith(str(self.workspace).lower()):
            raise ModelError(f"Ruta fuera del workspace. Usa archivos dentro de: {self.workspace}")
        return path

    def _project_dir(self, name: str) -> Path:
        if not NAME_RE.match(name):
            raise ModelError("Nombre de proyecto inválido: usa letras, números, '_', '-' o '.'")
        return self._safe_path(name)

    def _require_project(self) -> Path:
        if self.project is None:
            raise ModelError("No hay proyecto activo. Usa oems_new_project u oems_open_project.")
        return self.project

    def _model_path(self) -> Path:
        return self._require_project() / "model.json"

    def load_model(self) -> dict:
        mp = self._model_path()
        if not mp.exists():
            raise ModelError("El proyecto activo no tiene model.json (es un proyecto solo-script).")
        return json.loads(mp.read_text(encoding="utf-8"))

    def save_model(self, model: dict) -> None:
        model["modified"] = datetime.now().isoformat(timespec="seconds")
        self._model_path().write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")

    def _env(self) -> dict:
        env = os.environ.copy()
        env["CSXCAD_INSTALL_PATH"] = str(self.install_path)
        env["MPLBACKEND"] = "Agg"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    @staticmethod
    def _new_model(name: str) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "name": name, "created": now, "modified": now, "unit": "mm",
            "parameters": {},
            "frequency": None,
            "boundaries": ["MUR"] * 6,
            "air_margin_mm": None,
            "fdtd": {"max_timesteps": 30000, "end_criteria_db": -40.0},
            "mesh": {"divisor": 20, "smooth_ratio": 1.4, "thin_layer_cells": 4},
            "materials": {},
            "primitives": [],
            "ports": [],
            "nf2ff": {"enabled": False, "freqs_ghz": [], "theta_step_deg": 2.0},
            "generated_script_sha": None,
        }

    # ------------------------------------------------------------
    # PROYECTO Y WORKSPACE
    # ------------------------------------------------------------
    def status(self, mode: str, participant: str) -> str:
        run = self._run_state()
        running = "sí" if run and _pid_alive(run.get("pid", 0)) else "no"
        return (
            "openEMS MCP activo.\n"
            f"Modo: {mode}\n"
            f"Participante: {participant or '(sin definir)'}\n"
            f"Workspace: {self.workspace}\n"
            f"openEMS (CSXCAD_INSTALL_PATH): {self.install_path}\n"
            f"Python de simulación: {self.python}\n"
            f"Proyecto activo: {self.project.name if self.project else 'Ninguno'}\n"
            f"Simulación en curso: {running}"
        )

    def list_workspace_files(self, extension_filter: str = "") -> str:
        ext = extension_filter.lower().strip()
        files = []
        for p in sorted(self.workspace.rglob("*")):
            if p.is_file() and "sim" not in p.relative_to(self.workspace).parts[1:2]:
                if not ext or p.suffix.lower() == ext:
                    files.append(str(p.relative_to(self.workspace)))
        if not files:
            return f"No se encontraron archivos en {self.workspace} con filtro '{extension_filter}'."
        if len(files) > 400:
            files = files[:400] + [f"... ({len(files) - 400} más)"]
        return "Archivos del workspace:\n" + "\n".join(f"- {f}" for f in files)

    def new_project(self, name: str) -> str:
        d = self._project_dir(name)
        if d.exists():
            raise ModelError(f"El proyecto '{name}' ya existe. Usa oems_open_project.")
        d.mkdir(parents=True)
        self.project = d
        self.save_model(self._new_model(name))
        return f"Proyecto creado y activo: {d}"

    def open_project(self, name: str) -> str:
        d = self._project_dir(name)
        if not d.is_dir():
            raise ModelError(f"No existe el proyecto '{name}' en {self.workspace}")
        if not (d / "model.json").exists() and not (d / "simulate.py").exists():
            raise ModelError(f"'{name}' no contiene model.json ni simulate.py")
        self.project = d
        kind = "modelo + script" if (d / "model.json").exists() else "solo script (simulate.py)"
        return f"Proyecto activo: {d} ({kind})"

    def duplicate_project(self, new_name: str) -> str:
        model = self.load_model()
        d = self._project_dir(new_name)
        if d.exists():
            raise ModelError(f"El proyecto '{new_name}' ya existe.")
        d.mkdir(parents=True)
        model["name"] = new_name
        model["created"] = datetime.now().isoformat(timespec="seconds")
        model["generated_script_sha"] = None
        self.project = d
        self.save_model(model)
        return f"Proyecto duplicado como '{new_name}' (ahora es el activo). No se copiaron resultados."

    def close_project(self) -> str:
        name = self.project.name if self.project else None
        self.project = None
        return f"Proyecto '{name}' cerrado." if name else "No había proyecto activo."

    def query_setup(self) -> str:
        p = self._require_project()
        if not (p / "model.json").exists():
            return f"Proyecto solo-script: {p}\nRevisa simulate.py directamente."
        m = self.load_model()
        params = m["parameters"]
        out = [f"Proyecto: {m['name']} (modificado {m['modified']})"]
        fr = m["frequency"]
        out.append(f"Frecuencia: {fr['fmin_ghz']}–{fr['fmax_ghz']} GHz" if fr else "Frecuencia: SIN DEFINIR")
        out.append(f"Contornos: {m['boundaries']}")
        out.append(f"Margen de aire: {m['air_margin_mm'] or 'auto (lambda(f_min)/4)'} mm")
        out.append(f"FDTD: {m['fdtd']}  | Malla: {m['mesh']}")
        out.append(f"Campo lejano: {m['nf2ff']}")
        out.append("Parámetros: " + (", ".join(f"{k}={v}" for k, v in params.items()) or "(ninguno)"))
        out.append("Materiales:")
        for k, v in m["materials"].items():
            out.append(f"  - {k}: {v}")
        out.append("Primitivas:")
        for pr in m["primitives"]:
            out.append(f"  - {pr['name']} [{pr['kind']}, {pr['material']}]: "
                       + json.dumps({k: v for k, v in pr.items() if k not in ('name', 'kind', 'material')}, ensure_ascii=False))
        out.append("Puertos:")
        for pt in m["ports"]:
            out.append(f"  - {json.dumps(pt, ensure_ascii=False)}")
        return "\n".join(out)

    # ------------------------------------------------------------
    # CONFIGURACIÓN
    # ------------------------------------------------------------
    def set_frequency_range(self, fmin_ghz: float, fmax_ghz: float) -> str:
        if not 0 < fmin_ghz < fmax_ghz:
            raise ModelError("Se requiere 0 < fmin < fmax.")
        m = self.load_model()
        m["frequency"] = {"fmin_ghz": float(fmin_ghz), "fmax_ghz": float(fmax_ghz)}
        self.save_model(m)
        return f"Rango de frecuencia: {fmin_ghz}–{fmax_ghz} GHz (pulso gaussiano centrado en {(fmin_ghz + fmax_ghz) / 2:g} GHz)."

    def set_boundaries(self, boundaries: list[str]) -> str:
        bcs = [b.upper() for b in boundaries]
        if len(bcs) == 1:
            bcs = bcs * 6
        if len(bcs) != 6 or any(b not in BC_OPTIONS for b in bcs):
            raise ModelError(f"Se esperan 1 o 6 valores de {sorted(BC_OPTIONS)} (orden xmin,xmax,ymin,ymax,zmin,zmax).")
        m = self.load_model()
        m["boundaries"] = bcs
        self.save_model(m)
        return f"Contornos: {bcs}"

    def set_air_margin(self, margin_mm: float) -> str:
        m = self.load_model()
        m["air_margin_mm"] = None if margin_mm <= 0 else float(margin_mm)
        self.save_model(m)
        return "Margen de aire automático (lambda(f_min)/4)." if margin_mm <= 0 else f"Margen de aire: {margin_mm} mm por lado."

    def set_fdtd(self, max_timesteps: int, end_criteria_db: float) -> str:
        if max_timesteps < 1000 or end_criteria_db >= 0:
            raise ModelError("max_timesteps >= 1000 y end_criteria_db negativo (p. ej. -40).")
        m = self.load_model()
        m["fdtd"] = {"max_timesteps": int(max_timesteps), "end_criteria_db": float(end_criteria_db)}
        self.save_model(m)
        return f"FDTD: hasta {max_timesteps} pasos o caída de energía de {end_criteria_db} dB."

    def set_mesh(self, divisor: float, smooth_ratio: float, thin_layer_cells: int) -> str:
        if divisor < 5 or not 1.0 < smooth_ratio <= 2.0 or thin_layer_cells < 1:
            raise ModelError("divisor >= 5, 1 < smooth_ratio <= 2, thin_layer_cells >= 1.")
        m = self.load_model()
        m["mesh"] = {"divisor": float(divisor), "smooth_ratio": float(smooth_ratio), "thin_layer_cells": int(thin_layer_cells)}
        self.save_model(m)
        return f"Malla: celda máx = lambda_min/{divisor:g}, razón de suavizado {smooth_ratio}, {thin_layer_cells} celdas en capas delgadas."

    def set_nf2ff(self, enabled: bool, freqs_ghz: list[float], theta_step_deg: float) -> str:
        m = self.load_model()
        m["nf2ff"] = {"enabled": bool(enabled), "freqs_ghz": [float(x) for x in freqs_ghz],
                      "theta_step_deg": float(theta_step_deg)}
        self.save_model(m)
        if not enabled:
            return "Campo lejano desactivado."
        where = ", ".join(f"{x:g} GHz" for x in freqs_ghz) or "la frecuencia de resonancia"
        return f"Campo lejano activado: se calculará en {where} (paso theta {theta_step_deg}°)."

    # ------------------------------------------------------------
    # PARÁMETROS
    # ------------------------------------------------------------
    def set_parameters(self, values: dict) -> str:
        m = self.load_model()
        for k, v in values.items():
            if not k.isidentifier() or k in RESERVED_NAMES or k.startswith("_") or k in FUNCS or k in CONSTS:
                raise ModelError(f"Nombre de parámetro no permitido: '{k}' (reservado o inválido)")
            try:
                m["parameters"][k] = float(v)
            except (TypeError, ValueError):
                raise ModelError(f"El parámetro '{k}' debe ser numérico (recibido {v!r}).")
        self._validate(m)
        self.save_model(m)
        return "Parámetros: " + ", ".join(f"{k}={m['parameters'][k]:g}" for k in values)

    def delete_parameter(self, name: str) -> str:
        m = self.load_model()
        if name not in m["parameters"]:
            raise ModelError(f"No existe el parámetro '{name}'.")
        del m["parameters"][name]
        try:
            self._validate(m)
        except ModelError as e:
            raise ModelError(f"No se puede borrar '{name}': {e}")
        self.save_model(m)
        return f"Parámetro '{name}' eliminado."

    # ------------------------------------------------------------
    # MATERIALES
    # ------------------------------------------------------------
    def _add_material(self, name: str, data: dict) -> str:
        if not name.isidentifier():
            raise ModelError("Nombre de material inválido (usa letras, números y '_').")
        m = self.load_model()
        existed = name in m["materials"]
        m["materials"][name] = data
        self._validate(m)
        self.save_model(m)
        return f"Material '{name}' {'actualizado' if existed else 'creado'}: {data}"

    def create_dielectric(self, name: str, eps_r, tan_d, tan_d_freq_ghz: float) -> str:
        return self._add_material(name, {"type": "dielectric", "eps_r": norm_value(eps_r),
                                         "tan_d": norm_value(tan_d), "tan_d_freq_ghz": float(tan_d_freq_ghz)})

    def create_metal(self, name: str, sigma: float, thickness_um: float) -> str:
        if sigma > 0 and thickness_um > 0:
            return self._add_material(name, {"type": "conducting_sheet", "sigma": float(sigma),
                                             "thickness_um": float(thickness_um)})
        return self._add_material(name, {"type": "metal"})

    def delete_material(self, name: str) -> str:
        m = self.load_model()
        used = [p["name"] for p in m["primitives"] if p["material"] == name]
        if used:
            raise ModelError(f"El material '{name}' lo usan: {used}. Bórralas primero.")
        m["materials"].pop(name, None)
        self.save_model(m)
        return f"Material '{name}' eliminado."

    # ------------------------------------------------------------
    # GEOMETRÍA Y PUERTOS
    # ------------------------------------------------------------
    def _add_primitive(self, prim: dict) -> str:
        if not prim["name"].isidentifier():
            raise ModelError("Nombre de primitiva inválido (usa letras, números y '_').")
        m = self.load_model()
        if prim["material"] not in m["materials"]:
            raise ModelError(f"Material '{prim['material']}' no existe. Créalo primero.")
        replaced = any(p["name"] == prim["name"] for p in m["primitives"])
        m["primitives"] = [p for p in m["primitives"] if p["name"] != prim["name"]] + [prim]
        self._validate(m)
        self.save_model(m)
        return f"Primitiva '{prim['name']}' {'reemplazada' if replaced else 'creada'} ({prim['kind']}, {prim['material']})."

    def add_box(self, name, material, start, stop, priority) -> str:
        prim = {"name": name, "material": material, "kind": "box",
                "start": [norm_value(v) for v in start], "stop": [norm_value(v) for v in stop]}
        if priority is not None:
            prim["priority"] = int(priority)
        return self._add_primitive(prim)

    def add_cylinder(self, name, material, start, stop, radius, priority) -> str:
        prim = {"name": name, "material": material, "kind": "cylinder",
                "start": [norm_value(v) for v in start], "stop": [norm_value(v) for v in stop],
                "radius": norm_value(radius)}
        if priority is not None:
            prim["priority"] = int(priority)
        return self._add_primitive(prim)

    def add_polygon(self, name, material, points, normal, elevation, length, priority) -> str:
        if normal not in AXES:
            raise ModelError("normal debe ser 'x', 'y' o 'z'.")
        if len(points) < 3 or any(len(pt) != 2 for pt in points):
            raise ModelError("points debe ser una lista de al menos 3 pares [u, v].")
        prim = {"name": name, "material": material, "kind": "polygon", "normal": normal,
                "points": [[norm_value(a), norm_value(b)] for a, b in points],
                "elevation": norm_value(elevation), "length": norm_value(length)}
        if priority is not None:
            prim["priority"] = int(priority)
        return self._add_primitive(prim)

    def delete_primitive(self, name: str) -> str:
        m = self.load_model()
        before = len(m["primitives"])
        m["primitives"] = [p for p in m["primitives"] if p["name"] != name]
        if len(m["primitives"]) == before:
            raise ModelError(f"No existe la primitiva '{name}'.")
        self.save_model(m)
        return f"Primitiva '{name}' eliminada."

    def add_lumped_port(self, number, resistance, start, stop, direction, excite) -> str:
        if direction not in AXES:
            raise ModelError("direction debe ser 'x', 'y' o 'z'.")
        m = self.load_model()
        port = {"number": int(number), "resistance": norm_value(resistance), "direction": direction,
                "start": [norm_value(v) for v in start], "stop": [norm_value(v) for v in stop],
                "excite": bool(excite)}
        m["ports"] = sorted([p for p in m["ports"] if p["number"] != port["number"]] + [port],
                            key=lambda p: p["number"])
        self._validate(m)
        self.save_model(m)
        return f"Puerto {number} definido (R={resistance} ohm, dirección {direction}, {'excitado' if excite else 'pasivo'})."

    def delete_port(self, number: int) -> str:
        m = self.load_model()
        before = len(m["ports"])
        m["ports"] = [p for p in m["ports"] if p["number"] != number]
        if len(m["ports"]) == before:
            raise ModelError(f"No existe el puerto {number}.")
        self.save_model(m)
        return f"Puerto {number} eliminado."

    def _validate(self, m: dict) -> None:
        """Comprueba que todas las expresiones se puedan evaluar con los parámetros actuales."""
        P = m["parameters"]
        for name, mat in m["materials"].items():
            for key in ("eps_r", "tan_d"):
                if key in mat:
                    eval_expr(mat[key], P)
        for pr in m["primitives"]:
            for key in ("start", "stop"):
                if key in pr:
                    if len(pr[key]) != 3:
                        raise ModelError(f"{pr['name']}.{key} debe tener 3 coordenadas.")
                    [eval_expr(v, P) for v in pr[key]]
            if "radius" in pr:
                eval_expr(pr["radius"], P)
            if pr["kind"] == "polygon":
                [eval_expr(v, P) for pt in pr["points"] for v in pt]
                eval_expr(pr["elevation"], P)
                eval_expr(pr.get("length") or 0, P)
        for pt in m["ports"]:
            if len(pt["start"]) != 3 or len(pt["stop"]) != 3:
                raise ModelError(f"El puerto {pt['number']} necesita start/stop de 3 coordenadas.")
            s = [eval_expr(v, P) for v in pt["start"]]
            e = [eval_expr(v, P) for v in pt["stop"]]
            if eval_expr(pt["resistance"], P) <= 0:
                raise ModelError("La resistencia del puerto debe ser > 0.")
            d = AXES.index(pt["direction"])
            if s[d] == e[d]:
                raise ModelError(f"Puerto {pt['number']}: start y stop no pueden coincidir en la dirección {pt['direction']}.")

    # ------------------------------------------------------------
    # PLANTILLAS Y CÁLCULO
    # ------------------------------------------------------------
    @staticmethod
    def patch_calculator(freq_ghz: float, eps_r: float, h_mm: float, z0_ohm: float = 50.0) -> dict:
        """Modelo de línea de transmisión (Balanis) para un parche rectangular."""
        f = freq_ghz * 1e9
        lam0 = C0 / f * 1e3  # mm
        W = C0 / (2 * f) * math.sqrt(2 / (eps_r + 1)) * 1e3
        eps_eff = (eps_r + 1) / 2 + (eps_r - 1) / 2 * (1 + 12 * h_mm / W) ** -0.5
        dL = 0.412 * h_mm * ((eps_eff + 0.3) * (W / h_mm + 0.264)) / ((eps_eff - 0.258) * (W / h_mm + 0.8))
        L = C0 / (2 * f * math.sqrt(eps_eff)) * 1e3 - 2 * dL
        k0h = 2 * math.pi / lam0 * h_mm
        G1 = W / (120 * lam0) * (1 - k0h ** 2 / 24)
        R_edge = 1 / (2 * G1)
        y0 = L / math.pi * math.acos(math.sqrt(min(1.0, z0_ohm / R_edge)))
        return {
            "f_ghz": freq_ghz, "eps_r": eps_r, "h_mm": h_mm, "lambda0_mm": lam0,
            "W_mm": W, "eps_eff": eps_eff, "delta_L_mm": dL, "L_mm": L,
            "R_edge_ohm": R_edge, "feed_from_edge_mm": y0, "feed_from_center_mm": L / 2 - y0,
            "ground_min_mm": [L + 6 * h_mm, W + 6 * h_mm],
        }

    def create_microstrip_patch_template(self, freq_ghz, eps_r, tan_d, h_mm, L_mm, W_mm, feed_mm, with_farfield) -> str:
        calc = self.patch_calculator(freq_ghz, eps_r, h_mm)
        L = L_mm if L_mm > 0 else round(calc["L_mm"], 2)
        W = W_mm if W_mm > 0 else round(calc["W_mm"], 2)
        feed = feed_mm if feed_mm > 0 else round(calc["feed_from_center_mm"], 2)
        m = self.load_model()
        m["parameters"].update({"L": L, "W": W, "h": float(h_mm), "eps_r": float(eps_r), "tan_d": float(tan_d),
                                "feed": feed, "gnd_x": round(L + 6 * h_mm, 2), "gnd_y": round(W + 6 * h_mm, 2)})
        m["frequency"] = {"fmin_ghz": round(freq_ghz * 0.6, 4), "fmax_ghz": round(freq_ghz * 1.4, 4)}
        m["materials"]["sustrato"] = {"type": "dielectric", "eps_r": "eps_r", "tan_d": "tan_d", "tan_d_freq_ghz": float(freq_ghz)}
        m["materials"]["pec"] = {"type": "metal"}
        names = {"sustrato", "plano_tierra", "parche"}
        m["primitives"] = [p for p in m["primitives"] if p["name"] not in names] + [
            {"name": "sustrato", "material": "sustrato", "kind": "box",
             "start": ["-gnd_x/2", "-gnd_y/2", 0.0], "stop": ["gnd_x/2", "gnd_y/2", "h"]},
            {"name": "plano_tierra", "material": "pec", "kind": "box",
             "start": ["-gnd_x/2", "-gnd_y/2", 0.0], "stop": ["gnd_x/2", "gnd_y/2", 0.0]},
            {"name": "parche", "material": "pec", "kind": "box",
             "start": ["-L/2", "-W/2", "h"], "stop": ["L/2", "W/2", "h"]},
        ]
        m["ports"] = [{"number": 1, "resistance": 50.0, "direction": "z",
                       "start": ["-feed", 0.0, 0.0], "stop": ["-feed", 0.0, "h"], "excite": True}]
        m["nf2ff"] = {"enabled": bool(with_farfield), "freqs_ghz": [], "theta_step_deg": 2.0}
        self._validate(m)
        self.save_model(m)
        return (
            f"Plantilla de parche microstrip creada para {freq_ghz} GHz (alimentación por sonda, puerto concentrado 50 ohm).\n"
            f"Parámetros: L={L} mm (eje x, longitud resonante), W={W} mm, h={h_mm} mm, eps_r={eps_r}, "
            f"tan_d={tan_d}, feed={feed} mm desde el centro, plano de tierra {m['parameters']['gnd_x']}x{m['parameters']['gnd_y']} mm.\n"
            f"Valores teóricos (modelo de línea de transmisión): L={calc['L_mm']:.2f}, W={calc['W_mm']:.2f}, "
            f"eps_eff={calc['eps_eff']:.3f}, R_borde={calc['R_edge_ohm']:.0f} ohm.\n"
            f"Rango de simulación: {m['frequency']['fmin_ghz']}–{m['frequency']['fmax_ghz']} GHz."
        )

    # ------------------------------------------------------------
    # SCRIPT
    # ------------------------------------------------------------
    def _script_path(self) -> Path:
        return self._require_project() / "simulate.py"

    def generate_script(self, overwrite_edited: bool = False) -> tuple[Path, str]:
        m = self.load_model()
        if not m["frequency"]:
            raise ModelError("Define el rango de frecuencia antes de generar el script (oems_set_frequency_range).")
        if not m["ports"]:
            raise ModelError("El modelo no tiene puertos. Agrega uno con oems_add_lumped_port.")
        if not any(p.get("excite") for p in m["ports"]):
            raise ModelError("Ningún puerto está excitado (excite=True).")
        self._validate(m)
        sp = self._script_path()
        if sp.exists() and not overwrite_edited:
            sha = hashlib.sha256(sp.read_bytes()).hexdigest()
            if m.get("generated_script_sha") and sha != m["generated_script_sha"]:
                raise ModelError(
                    "simulate.py fue editado a mano después de generarse. No lo sobrescribo. "
                    "Usa overwrite_edited=True para regenerarlo desde model.json, o ejecútalo tal cual "
                    "con oems_run_simulation(regenerate=False).")
        code = generate_script(m)
        sp.write_text(code, encoding="utf-8")
        m["generated_script_sha"] = hashlib.sha256(sp.read_bytes()).hexdigest()
        self.save_model(m)
        return sp, code

    # ------------------------------------------------------------
    # EJECUCIÓN
    # ------------------------------------------------------------
    def _run_state_path(self) -> Path:
        return self.workspace / "_run_state.json"

    def _run_state(self) -> dict | None:
        p = self._run_state_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None

    def _is_running(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        st = self._run_state()
        return bool(st and st.get("status") == "running" and _pid_alive(st.get("pid", 0)))

    def _launch(self, cmd: list[str], cwd: Path, kind: str, log_name: str) -> dict:
        if self._is_running():
            raise ModelError("Ya hay una simulación en curso. Usa oems_simulation_status u oems_stop_simulation.")
        log = cwd / log_name
        fh = open(log, "w", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT,
                                      env=self._env(), creationflags=flags)
        fh.close()
        st = {"pid": self._proc.pid, "kind": kind, "cmd": cmd, "cwd": str(cwd), "log": str(log),
              "started": datetime.now().isoformat(timespec="seconds"), "status": "running"}
        self._run_state_path().write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st

    def _wait(self, max_wait_s: float) -> bool:
        t_end = time.time() + max_wait_s
        while time.time() < t_end:
            if not self._is_running():
                return True
            time.sleep(1.0)
        return False

    @staticmethod
    def _tail(log: Path, n: int = 15) -> list[str]:
        if not log.exists():
            return []
        return log.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]

    def _finish_state(self) -> dict | None:
        st = self._run_state()
        if not st:
            return None
        if st.get("status") == "running" and not self._is_running():
            code = self._proc.returncode if self._proc is not None and self._proc.pid == st["pid"] else None
            text = Path(st["log"]).read_text(encoding="utf-8", errors="replace") if Path(st["log"]).exists() else ""
            ok = (code == 0) if code is not None else ("Traceback" not in text)
            st["status"] = "finished" if ok else "failed"
            st["exit_code"] = code
            st["ended"] = datetime.now().isoformat(timespec="seconds")
            self._run_state_path().write_text(json.dumps(st, indent=2), encoding="utf-8")
        return st

    def run_simulation(self, regenerate: bool, wait: bool, max_wait_s: float, extra_args: list[str]) -> str:
        p = self._require_project()
        if regenerate and (p / "model.json").exists():
            self.generate_script()
        sp = self._script_path()
        if not sp.exists():
            raise ModelError("No existe simulate.py en el proyecto activo.")
        self._launch([self.python, "-u", str(sp)] + extra_args, p, "simulation", "simulation.log")
        return self._after_launch(wait, max_wait_s)

    def run_script(self, file_name: str, script_args: list[str], wait: bool, max_wait_s: float) -> str:
        sp = self._safe_path(file_name)
        if sp.suffix.lower() != ".py" or not sp.is_file():
            raise ModelError(f"No existe el script Python: {sp}")
        self._launch([self.python, "-u", str(sp)] + script_args, sp.parent, "script", f"{sp.stem}.log")
        return self._after_launch(wait, max_wait_s)

    def sweep_parameter(self, name: str, values: list[float], wait: bool, max_wait_s: float, with_farfield: bool) -> str:
        p = self._require_project()
        m = self.load_model()
        if name not in m["parameters"]:
            raise ModelError(f"'{name}' no es un parámetro del modelo.")
        if not values:
            raise ModelError("Lista de valores vacía.")
        self.generate_script()
        driver = Path(__file__).with_name("sweep_driver.py")
        cmd = [self.python, "-u", str(driver), str(self._script_path()), name, json.dumps([float(v) for v in values])]
        if not with_farfield:
            cmd.append("--no-ff")
        self._launch(cmd, p, "sweep", f"sweep_{name}.log")
        return self._after_launch(wait, max_wait_s, f"Barrido de '{name}' con {len(values)} valores")

    def _after_launch(self, wait: bool, max_wait_s: float, what: str = "Simulación") -> str:
        if not wait:
            return f"{what} lanzada en segundo plano. Consulta el avance con oems_simulation_status."
        if self._wait(max_wait_s):
            return self.simulation_status()
        return (f"{what} sigue corriendo tras {max_wait_s:.0f} s. "
                "Consulta oems_simulation_status más tarde; los resultados se guardan solos al terminar.")

    def simulation_status(self) -> str:
        st = self._finish_state()
        if not st:
            return "No se ha lanzado ninguna simulación en esta sesión del workspace."
        log = Path(st["log"])
        tail = self._tail(log, 400)
        progress = [l for l in tail if "Timestep:" in l]
        out = [f"Estado: {st['status']} ({st['kind']}) — iniciado {st['started']}" + (f", terminado {st.get('ended')}" if st.get('ended') else ""),
               f"Carpeta: {st['cwd']}", f"Log: {log}"]
        if progress:
            out.append("Último avance FDTD: " + progress[-1].strip())
        for l in tail:
            if l.startswith("MALLA_JSON:"):
                info = json.loads(l[len("MALLA_JSON:"):])
                out.append(f"Malla: {info['cells']:,} celdas, líneas {info['lines']}, margen de aire {info['air_margin_mm']:.1f} mm")
        ends = [l for l in tail if "end-criteria" in l or "max. number of timesteps" in l.lower()]
        if ends:
            out.append(ends[-1].strip())
        if st["status"] == "failed":
            out.append("ERROR. Últimas líneas del log:")
            out.extend("  " + l for l in tail[-15:])
        elif st["status"] == "finished":
            summaries = [l for l in tail if l.startswith("RESUMEN_JSON:") or l.startswith("BARRIDO_JSON:")]
            if summaries:
                out.append("Resultado: " + summaries[-1].split(":", 1)[1])
            elif st["kind"] == "script":
                out.extend("  " + l for l in tail[-10:])
        return "\n".join(out)

    def stop_simulation(self) -> str:
        st = self._run_state()
        if not st or not self._is_running():
            return "No hay simulación en curso."
        subprocess.run(["taskkill", "/PID", str(st["pid"]), "/T", "/F"], capture_output=True)
        st["status"] = "stopped"
        st["ended"] = datetime.now().isoformat(timespec="seconds")
        self._run_state_path().write_text(json.dumps(st, indent=2), encoding="utf-8")
        return f"Simulación detenida (PID {st['pid']})."

    def preview_mesh(self) -> str:
        p = self._require_project()
        if (p / "model.json").exists():
            self.generate_script()
        sp = self._script_path()
        r = subprocess.run([self.python, "-u", str(sp), "--dry"], cwd=str(p), env=self._env(),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        line = next((l for l in r.stdout.splitlines() if l.startswith("MALLA_JSON:")), None)
        if r.returncode != 0 or not line:
            raise ModelError("Falló la construcción del modelo:\n" + (r.stdout + r.stderr)[-2500:])
        info = json.loads(line[len("MALLA_JSON:"):])
        cells = info["cells"]
        est_steps = 10000
        est_s = cells * est_steps / 11e6  # ~11 MCells/s medido en este equipo
        return (
            f"Modelo construido sin simular (model.xml en results/).\n"
            f"Celdas: {cells:,}  (líneas x/y/z: {info['lines']})\n"
            f"Celda mínima (mm): {[round(x, 3) for x in info['min_cell_mm']]}  | máxima: {[round(x, 2) for x in info['max_cell_mm']]}\n"
            f"Resolución objetivo: {info['mesh_res_mm']:.2f} mm  | margen de aire: {info['air_margin_mm']:.1f} mm\n"
            f"Caja de simulación (mm): {[[round(a, 1), round(b, 1)] for a, b in info['sim_box_mm']]}\n"
            f"Paso temporal (Courant): {info['dt_courant_s']:.3e} s\n"
            f"Tiempo estimado: ~{est_s / 60:.1f} min (suponiendo ~{est_steps} pasos a ~11 MCeldas/s)."
        )

    def open_viewer(self) -> str:
        p = self._require_project()
        xml = p / "results" / "model.xml"
        if not xml.exists():
            self.preview_mesh()
        exe = self.install_path / "AppCSXCAD.exe"
        if not exe.exists():
            raise ModelError(f"No encontré AppCSXCAD.exe en {self.install_path}")
        subprocess.Popen([str(exe), str(xml)], cwd=str(p), env=self._env())
        return f"Abriendo {xml.name} en AppCSXCAD (visor 3D de la geometría y la malla)."

    # ------------------------------------------------------------
    # RESULTADOS
    # ------------------------------------------------------------
    def _results_dir(self, tag: str = "") -> Path:
        d = self._require_project() / "results"
        return d / tag if tag else d

    def get_results(self, tag: str = "") -> dict:
        f = self._results_dir(tag) / "summary.json"
        if not f.exists():
            raise ModelError(f"No hay resultados en {f.parent}. Ejecuta la simulación primero.")
        data = json.loads(f.read_text(encoding="utf-8"))
        data["files"] = sorted(str(x.relative_to(self.workspace)) for x in f.parent.iterdir()
                               if x.is_file() and x.suffix in (".csv", ".png", ".s1p", ".json", ".xml"))
        return data

    def farfield_evaluate(self, freqs_ghz: list[float], tag: str, max_wait_s: float) -> str:
        if not freqs_ghz:
            raise ModelError("Indica al menos una frecuencia en GHz.")
        args = ["--post-only"] + [a for f in freqs_ghz for a in ("--ff-freq", str(float(f)))]
        if tag:
            args += ["--tag", tag]
        return self.run_simulation(regenerate=False, wait=True, max_wait_s=max_wait_s, extra_args=args)

    def sweep_results(self, name: str) -> str:
        f = self._results_dir() / f"sweep_{name}.csv"
        if not f.exists():
            raise ModelError(f"No existe {f.name}. Ejecuta oems_sweep_parameter primero.")
        return f"{f.relative_to(self.workspace)}\n" + f.read_text(encoding="utf-8")

    # ------------------------------------------------------------
    # REVISIÓN Y REPORTE
    # ------------------------------------------------------------
    def design_check(self) -> str:
        p = self._require_project()
        items: list[tuple[str, str]] = []
        mesh_info_f = p / "results" / "mesh_info.json"
        if (p / "model.json").exists():
            m = self.load_model()
            P = m["parameters"]
            try:
                self._validate(m)
                items.append(("OK", "Todas las expresiones se evalúan con los parámetros actuales."))
            except ModelError as e:
                items.append(("ERROR", str(e)))
            fr = m["frequency"]
            if not fr:
                items.append(("ERROR", "No hay rango de frecuencia."))
            else:
                ratio = fr["fmax_ghz"] / fr["fmin_ghz"]
                items.append(("OK" if ratio <= 4 else "AVISO",
                              f"Rango {fr['fmin_ghz']}–{fr['fmax_ghz']} GHz (relación {ratio:.2f})."
                              + ("" if ratio <= 4 else " Un rango muy ancho alarga la simulación.")))
            exc = [pt for pt in m["ports"] if pt.get("excite")]
            if not m["ports"]:
                items.append(("ERROR", "No hay puertos."))
            elif len(exc) != 1:
                items.append(("AVISO" if exc else "ERROR", f"Puertos excitados: {len(exc)} (se espera 1)."))
            else:
                items.append(("OK", f"{len(m['ports'])} puerto(s), uno excitado."))
            # el puerto debe unir dos conductores
            try:
                metal_planes = {ax: set() for ax in AXES}
                for pr in m["primitives"]:
                    if m["materials"][pr["material"]]["type"] != "dielectric" and pr["kind"] == "box":
                        for i, ax in enumerate(AXES):
                            metal_planes[ax].add(round(eval_expr(pr["start"][i], P), 6))
                            metal_planes[ax].add(round(eval_expr(pr["stop"][i], P), 6))
                for pt in m["ports"]:
                    d = AXES.index(pt["direction"])
                    ends = {round(eval_expr(pt["start"][d], P), 6), round(eval_expr(pt["stop"][d], P), 6)}
                    if not ends <= metal_planes[pt["direction"]]:
                        items.append(("AVISO", f"Puerto {pt['number']}: sus extremos en {pt['direction']} no coinciden "
                                               "con caras de metales tipo caja. Verifica que conecte dos conductores."))
            except (ModelError, KeyError):
                pass
            if fr:
                lam_max = C0 / (fr["fmin_ghz"] * 1e9) * 1e3
                mg = m["air_margin_mm"]
                if mg is not None and mg < lam_max / 4 and any(b in ("MUR", "PML_8") for b in m["boundaries"]):
                    items.append(("AVISO", f"Margen de aire {mg} mm < lambda(f_min)/4 = {lam_max / 4:.1f} mm; "
                                           "los contornos absorbentes pueden afectar S11 y el campo lejano."))
                else:
                    items.append(("OK", "Margen de aire suficiente para contornos absorbentes."))
            if m["mesh"]["divisor"] < 15:
                items.append(("AVISO", f"Malla gruesa (lambda/{m['mesh']['divisor']:g}); se recomienda >= 15–20."))
            eps_max = max([eval_expr(v.get("eps_r", 1), P) for v in m["materials"].values() if v["type"] == "dielectric"] or [1])
            if m["mesh"]["divisor"] / math.sqrt(eps_max) < 10:
                items.append(("AVISO", f"Dentro del dieléctrico (eps_r={eps_max:g}) la celda equivale a "
                                       f"lambda/{m['mesh']['divisor'] / math.sqrt(eps_max):.1f}; considera subir el divisor."))
            if m["mesh"]["thin_layer_cells"] < 3:
                items.append(("AVISO", "Menos de 3 celdas en capas delgadas: el campo en el sustrato queda mal resuelto."))
            if m["fdtd"]["end_criteria_db"] > -30:
                items.append(("AVISO", f"Criterio de fin {m['fdtd']['end_criteria_db']} dB: la energía puede no decaer lo "
                                       "suficiente (recomendado -40 dB)."))
            if not m["nf2ff"]["enabled"]:
                items.append(("INFO", "Campo lejano desactivado: no habrá ganancia ni patrón."))
        else:
            items.append(("INFO", "Proyecto solo-script: revisión limitada a la malla (ejecuta oems_preview_mesh)."))
        if mesh_info_f.exists():
            info = json.loads(mesh_info_f.read_text(encoding="utf-8"))
            lvl = "OK" if info["cells"] < 2e6 else "AVISO"
            items.append((lvl, f"Última malla: {info['cells']:,} celdas" + ("" if lvl == "OK" else " (simulación lenta)") + "."))
            ratios = [mx / mn for mx, mn in zip(info["max_cell_mm"], info["min_cell_mm"]) if mn > 0]
            if ratios and max(ratios) > 50:
                items.append(("INFO", f"Relación celda máx/mín hasta {max(ratios):.0f}: paso temporal pequeño por celdas finas."))
        order = {"ERROR": 0, "AVISO": 1, "INFO": 2, "OK": 3}
        items.sort(key=lambda x: order[x[0]])
        return "Revisión del diseño:\n" + "\n".join(f"[{lvl}] {msg}" for lvl, msg in items)

    def generate_markdown_report(self, title: str, tag: str = "") -> str:
        p = self._require_project()
        res = self.get_results(tag)
        rd = self._results_dir(tag)
        lines = [f"# {title or 'Reporte openEMS: ' + p.name}", "",
                 f"Proyecto: `{p.name}`  ", f"Fecha: {datetime.now():%Y-%m-%d %H:%M}", ""]
        if (p / "model.json").exists():
            m = self.load_model()
            lines += ["## Parámetros", "", "| Parámetro | Valor |", "|---|---|"]
            lines += [f"| {k} | {v:g} |" for k, v in res.get("params", m["parameters"]).items()]
            lines += ["", "## Materiales", "", "| Material | Definición |", "|---|---|"]
            lines += [f"| {k} | {json.dumps(v, ensure_ascii=False)} |" for k, v in m["materials"].items()]
            fr = m["frequency"]
            lines += ["", "## Configuración", "",
                      f"- Rango de frecuencia: {fr['fmin_ghz']}–{fr['fmax_ghz']} GHz",
                      f"- Contornos: {', '.join(m['boundaries'])}",
                      f"- Malla: lambda_min/{m['mesh']['divisor']:g}, celdas simuladas: {res.get('cells', 0):,}",
                      f"- Criterio de fin: {m['fdtd']['end_criteria_db']} dB"]
        lines += ["", "## Resultados", "",
                  f"- Frecuencia de resonancia (mínimo de S11): **{res['f_res_ghz']:.4f} GHz**",
                  f"- S11 mínimo: **{res['s11_min_db']:.2f} dB**",
                  f"- Zin en resonancia: {res['zin_at_fres_ohm'][0]:.1f} {res['zin_at_fres_ohm'][1]:+.1f}j ohm"]
        bw = res.get("bw_10db")
        if bw:
            lines.append(f"- Ancho de banda (S11 < -10 dB): {bw['f_low_ghz']:.4f}–{bw['f_high_ghz']:.4f} GHz "
                         f"= {bw['bw_mhz']:.1f} MHz ({bw['fbw_pct']:.2f} %)")
        else:
            lines.append("- No hay banda con S11 < -10 dB.")
        for ff in res.get("farfield", []):
            lines.append(f"- A {ff['f_ghz']:.4g} GHz: directividad {ff['Dmax_dBi']:.2f} dBi, eficiencia de radiación "
                         f"{ff['rad_efficiency_pct']:.1f} %, ganancia realizada {ff['realized_gain_dBi']:.2f} dBi")
        lines += ["", "## Gráficas", ""]
        for img in sorted(rd.glob("*.png")):
            lines.append(f"![{img.stem}]({img.relative_to(p).as_posix()})")
        lines += ["", "---", "Generado con mcp-openems a partir de `simulate.py` (openEMS, método FDTD)."]
        out = p / (f"reporte_{tag}.md" if tag else "reporte.md")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"Reporte escrito en {out}"
