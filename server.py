# -*- coding: utf-8 -*-
"""
Servidor MCP para openEMS (FDTD), análogo a mcp-cst-studio.

Variables de entorno:
  OPENEMS_WORKSPACE        carpeta de trabajo (por defecto C:\\OPENEMS_MCP_WORK)
  CSXCAD_INSTALL_PATH      carpeta con openEMS.exe y CSXCAD.dll (por defecto C:\\openEMS-0.37.0)
  OPENEMS_MCP_MODE         "full" (por defecto) o "tutor": en modo tutor no se registran
                           las herramientas que diseñan o modifican el modelo.
  OPENEMS_MCP_PARTICIPANT  código del participante, se guarda en el registro de llamadas.
"""
import functools
import json
import os
import time
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from openems_bridge import ModelError, OpenEMSBridge

MODE = os.getenv("OPENEMS_MCP_MODE", "full").strip().lower()
if MODE not in ("full", "tutor"):
    MODE = "full"
PARTICIPANT = os.getenv("OPENEMS_MCP_PARTICIPANT", "").strip()

mcp = FastMCP("openEMS MCP")
oems = OpenEMSBridge()
DISABLED: list[str] = []


def _log(tool: str, kwargs: dict, ok: bool, result: str, ms: int) -> None:
    """Registro JSONL de cada llamada: es el dato de interacción agente-software del estudio."""
    try:
        d = oems.workspace / "_logs"
        d.mkdir(exist_ok=True)
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"), "participant": PARTICIPANT,
            "mode": MODE, "tool": tool, "project": oems.project.name if oems.project else None,
            "args": kwargs, "ok": ok, "ms": ms, "result": result[:500],
        }
        with open(d / f"mcp_calls_{datetime.now():%Y%m%d}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def tool(design: bool = False):
    """Registra la herramienta con registro de llamadas. design=True: se oculta en modo tutor."""
    def deco(fn):
        if design and MODE == "tutor":
            DISABLED.append(fn.__name__)
            return fn

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                result, ok = fn(*args, **kwargs), True
            except ModelError as e:
                result, ok = f"Error: {e}", False
            except Exception as e:  # noqa: BLE001 - se informa al agente en vez de cortar la sesión
                result, ok = f"Error inesperado: {type(e).__name__}: {e}", False
            if not isinstance(result, str):
                result = json.dumps(result, indent=2, ensure_ascii=False)
            _log(fn.__name__, kwargs, ok, result, int((time.time() - t0) * 1000))
            return result

        return mcp.tool()(wrapper)
    return deco


# ============================================================
# PROYECTO Y WORKSPACE
# ============================================================

@tool()
def oems_status() -> str:
    """Muestra el estado del servidor: modo (full/tutor), workspace, proyecto activo y simulación en curso."""
    s = oems.status(MODE, PARTICIPANT)
    if DISABLED:
        s += "\nHerramientas deshabilitadas en modo tutor: " + ", ".join(DISABLED)
    return s


@tool()
def oems_list_workspace_files(extension_filter: str = "") -> str:
    """
    Lista archivos del workspace (omite los datos crudos de simulación).
    extension_filter opcional: ".py", ".json", ".csv", ".png", ".md".
    """
    return oems.list_workspace_files(extension_filter)


@tool(design=True)
def oems_new_project(name: str) -> str:
    """
    Crea un proyecto openEMS vacío (carpeta con model.json) y lo deja activo.
    Ejemplo: oems_new_project("parche_2g4")
    """
    return oems.new_project(name)


@tool()
def oems_open_project(name: str) -> str:
    """
    Activa un proyecto existente del workspace. Acepta proyectos con model.json
    o proyectos solo-script (una carpeta con simulate.py escrito por el estudiante).
    """
    return oems.open_project(name)


@tool(design=True)
def oems_duplicate_project(new_name: str) -> str:
    """Copia el modelo del proyecto activo a un proyecto nuevo (p. ej. para una versión v2) y lo activa."""
    return oems.duplicate_project(new_name)


@tool()
def oems_close_project() -> str:
    """Deja de usar el proyecto activo (los archivos ya están guardados)."""
    return oems.close_project()


@tool()
def oems_query_setup() -> str:
    """Describe el modelo activo: frecuencia, contornos, malla, parámetros, materiales, primitivas y puertos."""
    return oems.query_setup()


# ============================================================
# CONFIGURACIÓN DE LA SIMULACIÓN
# ============================================================

@tool(design=True)
def oems_set_frequency_range(fmin_ghz: float, fmax_ghz: float) -> str:
    """
    Define el rango de frecuencia (GHz). El pulso gaussiano de excitación cubre este rango.
    Ejemplo: oems_set_frequency_range(1.5, 3.5)
    """
    return oems.set_frequency_range(fmin_ghz, fmax_ghz)


@tool(design=True)
def oems_set_boundaries(boundaries: list[str]) -> str:
    """
    Condiciones de contorno: 1 valor para las 6 caras o 6 valores (xmin,xmax,ymin,ymax,zmin,zmax).
    Opciones: "MUR" (absorbente simple, por defecto), "PML_8" (absorbente mejor), "PEC", "PMC".
    """
    return oems.set_boundaries(boundaries)


@tool(design=True)
def oems_set_air_margin(margin_mm: float = 0.0) -> str:
    """Margen de aire entre la geometría y el contorno, en mm. 0 = automático (lambda(f_min)/4)."""
    return oems.set_air_margin(margin_mm)


@tool(design=True)
def oems_set_fdtd(max_timesteps: int = 30000, end_criteria_db: float = -40.0) -> str:
    """Criterio de parada FDTD: máximo de pasos y caída de energía en dB (p. ej. -40)."""
    return oems.set_fdtd(max_timesteps, end_criteria_db)


@tool(design=True)
def oems_set_mesh(divisor: float = 20.0, smooth_ratio: float = 1.4, thin_layer_cells: int = 4) -> str:
    """
    Malla: celda máxima = lambda_min/divisor; smooth_ratio limita el crecimiento entre celdas
    vecinas; thin_layer_cells = celdas a lo largo de capas delgadas (sustrato).
    """
    return oems.set_mesh(divisor, smooth_ratio, thin_layer_cells)


@tool(design=True)
def oems_set_farfield(enabled: bool = True, freqs_ghz: list[float] | None = None, theta_step_deg: float = 2.0) -> str:
    """
    Activa el cálculo de campo lejano (directividad, eficiencia, ganancia y patrón en phi=0/90).
    freqs_ghz vacío = se calcula en la frecuencia de resonancia (mínimo de S11).
    """
    return oems.set_nf2ff(enabled, freqs_ghz or [], theta_step_deg)


# ============================================================
# PARÁMETROS
# ============================================================

@tool(design=True)
def oems_set_parameter(name: str, value: float) -> str:
    """
    Define o actualiza un parámetro numérico (mm o adimensional).
    Las coordenadas pueden usarlo en expresiones, p. ej. "-L/2" o "h + 0.035".
    """
    return oems.set_parameters({name: value})


@tool(design=True)
def oems_set_parameters_batch(parameters_json: str) -> str:
    """
    Define varios parámetros con JSON.
    Ejemplo: {"L": 29.4, "W": 38.0, "h": 1.6}
    """
    try:
        values = json.loads(parameters_json)
    except json.JSONDecodeError as e:
        raise ModelError(f"JSON inválido: {e}")
    if not isinstance(values, dict):
        raise ModelError("Se espera un objeto JSON {nombre: valor}.")
    return oems.set_parameters(values)


@tool(design=True)
def oems_delete_parameter(name: str) -> str:
    """Elimina un parámetro (falla si alguna expresión lo usa)."""
    return oems.delete_parameter(name)


# ============================================================
# MATERIALES
# ============================================================

@tool(design=True)
def oems_create_dielectric(name: str, eps_r: float | str, tan_d: float | str = 0.0, tan_d_freq_ghz: float = 1.0) -> str:
    """
    Crea o actualiza un dieléctrico. eps_r y tan_d aceptan número o parámetro (p. ej. "eps_r").
    Las pérdidas se modelan con conductividad equivalente evaluada en tan_d_freq_ghz.
    """
    return oems.create_dielectric(name, eps_r, tan_d, tan_d_freq_ghz)


@tool(design=True)
def oems_create_fr4_material(name: str = "FR4", eps_r: float = 4.3, tan_d: float = 0.025, tan_d_freq_ghz: float = 2.45) -> str:
    """Atajo para FR-4 (eps_r 4.3, tan_d 0.025 por defecto)."""
    return oems.create_dielectric(name, eps_r, tan_d, tan_d_freq_ghz)


@tool(design=True)
def oems_create_metal(name: str = "pec", sigma: float = 0.0, thickness_um: float = 0.0) -> str:
    """
    Crea un metal. Sin sigma/espesor: conductor perfecto (PEC).
    Con sigma (S/m) y thickness_um: lámina conductora con pérdidas (solo para láminas 2D),
    p. ej. cobre sigma=5.8e7, thickness_um=35.
    """
    return oems.create_metal(name, sigma, thickness_um)


@tool(design=True)
def oems_delete_material(name: str) -> str:
    """Elimina un material que no use ninguna primitiva."""
    return oems.delete_material(name)


# ============================================================
# GEOMETRÍA Y PUERTOS
# ============================================================

@tool(design=True)
def oems_add_box(name: str, material: str, start: list[float | str], stop: list[float | str], priority: int | None = None) -> str:
    """
    Agrega (o reemplaza) una caja entre start y stop [x, y, z] en mm; admite expresiones.
    Una caja con espesor cero en un eje es una lámina (p. ej. parche o plano de tierra).
    Ejemplo: oems_add_box("parche", "pec", ["-L/2", "-W/2", "h"], ["L/2", "W/2", "h"])
    priority: mayor gana en solapes (por defecto metales 10, dieléctricos 0).
    """
    return oems.add_box(name, material, start, stop, priority)


@tool(design=True)
def oems_add_cylinder(name: str, material: str, start: list[float | str], stop: list[float | str], radius: float | str,
                      priority: int | None = None) -> str:
    """Agrega un cilindro de eje start→stop [x, y, z] y radio en mm (p. ej. una sonda coaxial o un dipolo)."""
    return oems.add_cylinder(name, material, start, stop, radius, priority)


@tool(design=True)
def oems_add_polygon(name: str, material: str, points: list[list[float | str]], normal: str = "z",
                     elevation: float | str = 0.0, length: float | str = 0.0, priority: int | None = None) -> str:
    """
    Agrega un polígono plano. points = [[u, v], ...] en el plano perpendicular a 'normal'
    (normal z → (x, y); normal x → (y, z); normal y → (z, x)), a la altura 'elevation'.
    length > 0 lo extruye en la dirección normal (sólido).
    """
    return oems.add_polygon(name, material, points, normal, elevation, length, priority)


@tool(design=True)
def oems_delete_primitive(name: str) -> str:
    """Elimina una primitiva por nombre."""
    return oems.delete_primitive(name)


@tool(design=True)
def oems_add_lumped_port(number: int, start: list[float | str], stop: list[float | str], direction: str = "z",
                         resistance: float | str = 50.0, excite: bool = True) -> str:
    """
    Puerto concentrado (resistencia + fuente) entre start y stop, orientado en 'direction'.
    Debe unir dos conductores, p. ej. del plano de tierra (z=0) al parche (z=h).
    """
    return oems.add_lumped_port(number, resistance, start, stop, direction, excite)


@tool(design=True)
def oems_delete_port(number: int) -> str:
    """Elimina un puerto por número."""
    return oems.delete_port(number)


# ============================================================
# PLANTILLAS Y CÁLCULO DE DISEÑO
# ============================================================

@tool(design=True)
def oems_patch_calculator(freq_ghz: float, eps_r: float = 4.3, h_mm: float = 1.6, z0_ohm: float = 50.0) -> str:
    """
    Dimensiones teóricas de un parche rectangular (modelo de línea de transmisión, Balanis):
    W, eps_eff, extensión de borde, L, resistencia de borde y posición de la sonda para z0_ohm.
    """
    r = oems.patch_calculator(freq_ghz, eps_r, h_mm, z0_ohm)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}


@tool(design=True)
def oems_create_microstrip_patch_template(freq_ghz: float = 2.45, eps_r: float = 4.3, tan_d: float = 0.02,
                                         h_mm: float = 1.6, L_mm: float = 0.0, W_mm: float = 0.0,
                                         feed_mm: float = 0.0, with_farfield: bool = True) -> str:
    """
    Crea en el proyecto activo un parche microstrip completo y parametrizado: sustrato,
    plano de tierra, parche, puerto concentrado de 50 ohm (sonda), rango de frecuencia y campo lejano.
    L_mm/W_mm/feed_mm = 0 → se calculan con el modelo de línea de transmisión.
    """
    return oems.create_microstrip_patch_template(freq_ghz, eps_r, tan_d, h_mm, L_mm, W_mm, feed_mm, with_farfield)


# ============================================================
# SCRIPT, MALLA Y SIMULACIÓN
# ============================================================

@tool(design=True)
def oems_generate_script(return_code: bool = False, overwrite_edited: bool = False) -> str:
    """
    Genera simulate.py (script openEMS legible) desde model.json.
    return_code=True devuelve además el código, para mostrarlo o explicarlo al estudiante.
    No sobrescribe un simulate.py editado a mano salvo overwrite_edited=True.
    """
    path, code = oems.generate_script(overwrite_edited)
    msg = f"Script generado: {path} ({len(code.splitlines())} líneas)."
    return msg + ("\n\n" + code if return_code else "")


@tool()
def oems_preview_mesh() -> str:
    """
    Construye el modelo y la malla SIN simular (segundos): número de celdas, tamaños de celda,
    caja de simulación y tiempo estimado. Úsalo antes de oems_run_simulation.
    """
    return oems.preview_mesh()


@tool()
def oems_open_viewer() -> str:
    """Abre la geometría y la malla en AppCSXCAD (visor 3D de openEMS) en el escritorio."""
    return oems.open_viewer()


@tool()
def oems_run_simulation(wait: bool = True, max_wait_s: float = 540.0, regenerate: bool = True) -> str:
    """
    Ejecuta simulate.py del proyecto activo (FDTD + post-proceso: S11, Zin, ancho de banda,
    campo lejano). wait=True espera hasta max_wait_s y devuelve el resumen; si no termina,
    sigue en segundo plano. regenerate=False ejecuta el script tal cual (p. ej. editado a mano).
    En modo tutor nunca se regenera el script.
    """
    return oems.run_simulation(regenerate and MODE != "tutor", wait, max_wait_s, [])


@tool()
def oems_run_script(file_name: str, script_args: list[str] | None = None, wait: bool = True,
                    max_wait_s: float = 540.0) -> str:
    """
    Ejecuta un script Python del workspace con el entorno openEMS (p. ej. el script que escribió
    el estudiante: "grupo3/simulate.py"). La salida queda en <script>.log junto al archivo.
    """
    return oems.run_script(file_name, script_args or [], wait, max_wait_s)


@tool()
def oems_simulation_status() -> str:
    """Estado de la última simulación: avance FDTD, malla, criterio de fin y resumen o error."""
    return oems.simulation_status()


@tool()
def oems_stop_simulation() -> str:
    """Detiene la simulación en curso."""
    return oems.stop_simulation()


@tool(design=True)
def oems_sweep_parameter(name: str, values: list[float], wait: bool = False, max_wait_s: float = 540.0,
                         with_farfield: bool = False) -> str:
    """
    Barrido paramétrico: una simulación por valor (en serie, en segundo plano por defecto).
    Resultado en results/sweep_<name>.csv (f_res, S11 mín, ancho de banda, Zin).
    Ejemplo: oems_sweep_parameter("L", [28.5, 29.0, 29.5])
    """
    return oems.sweep_parameter(name, values, wait, max_wait_s, with_farfield)


# ============================================================
# RESULTADOS
# ============================================================

@tool()
def oems_get_results(tag: str = "") -> str:
    """
    Resumen de la última simulación (results/summary.json): f de resonancia, S11 mínimo,
    Zin, ancho de banda a -10 dB, directividad, eficiencia, ganancia y lista de archivos.
    tag = subcarpeta de una corrida concreta (p. ej. de un barrido).
    """
    return oems.get_results(tag)


@tool()
def oems_read_result_csv(file_name: str, max_rows: int = 60) -> str:
    """
    Lee un CSV de resultados del workspace (p. ej. "parche/results/s11.csv"), submuestreado
    a max_rows filas para analizarlo sin saturar el contexto.
    """
    p = oems._safe_path(file_name)
    if p.suffix.lower() != ".csv" or not p.is_file():
        raise ModelError(f"No existe el CSV {p}")
    lines = p.read_text(encoding="utf-8").splitlines()
    header, rows = lines[0], lines[1:]
    step = max(1, len(rows) // max(1, max_rows))
    return f"{p.name}: {len(rows)} filas (mostrando 1 de cada {step})\n" + "\n".join([header] + rows[::step])


@tool()
def oems_farfield_evaluate(freqs_ghz: list[float], tag: str = "", max_wait_s: float = 300.0) -> str:
    """
    Recalcula el campo lejano en otras frecuencias (GHz) sin volver a simular
    (requiere que el campo lejano estuviera activo en la simulación).
    """
    return oems.farfield_evaluate(freqs_ghz, tag, max_wait_s)


@tool()
def oems_sweep_results(name: str) -> str:
    """Tabla del barrido del parámetro 'name' (results/sweep_<name>.csv)."""
    return oems.sweep_results(name)


# ============================================================
# REVISIÓN Y REPORTE
# ============================================================

@tool()
def oems_design_check() -> str:
    """
    Revisa el modelo sin simular: expresiones, puertos (que unan dos conductores), margen de aire,
    resolución de malla en el dieléctrico, capas delgadas, criterio de fin y tamaño de la malla.
    Devuelve una lista ERROR/AVISO/INFO/OK.
    """
    return oems.design_check()


@tool()
def oems_generate_markdown_report(title: str = "", tag: str = "") -> str:
    """Escribe reporte.md en el proyecto: parámetros, materiales, configuración, resultados y gráficas."""
    return oems.generate_markdown_report(title, tag)


if __name__ == "__main__":
    mcp.run()
