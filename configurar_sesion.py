# -*- coding: utf-8 -*-
"""
Prepara una sesión del estudio en Claude Code (pestaña Code de Claude Desktop o CLI).

Escribe en el workspace (que es también la carpeta de trabajo de Claude Code):
  .mcp.json              servidor openems con el modo y el código del participante
  .claude/settings.json  permisos: solo herramientas oems_* y lectura de archivos; todo lo demás se deniega
  CLAUDE.md              instrucciones del agente para el modo y la tarea (desde materiales/prompts)

    python configurar_sesion.py --modo tutor --tarea dipolo --participante P07
    python configurar_sesion.py --mostrar

La configuración se lee al abrir la sesión: abre una sesión NUEVA de Claude Code en el workspace
después de ejecutar este script.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = Path(os.getenv("OPENEMS_WORKSPACE", r"C:\OPENEMS_MCP_WORK"))
PROMPTS = Path(os.getenv("OPENEMS_PROMPTS", str(HERE / "prompts")))
INSTALL = os.getenv("CSXCAD_INSTALL_PATH", r"C:\openEMS-0.37.0")

# Herramientas incorporadas que nunca se permiten: ejecutar código, escribir archivos, web y subagentes.
DENY = ["Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task"]
ALLOW = ["mcp__openems", "Read", "Glob", "Grep"]


def settings() -> dict:
    return {
        "permissions": {"defaultMode": "dontAsk", "allow": ALLOW, "deny": DENY},
        "enabledMcpjsonServers": ["openems"],
        "enableAllProjectMcpServers": False,
    }


def mcp_config(modo: str, participante: str, ws: Path) -> dict:
    return {"mcpServers": {"openems": {
        "command": str(HERE / ".venv" / "Scripts" / "python.exe"),
        "args": ["-u", str(HERE / "server.py")],
        "env": {
            "CSXCAD_INSTALL_PATH": INSTALL,
            "OPENEMS_WORKSPACE": str(ws),
            "OPENEMS_MCP_MODE": modo,
            "OPENEMS_MCP_PARTICIPANT": participante,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    }}}


def main():
    ap = argparse.ArgumentParser(description="Configura una sesión openEMS + Claude Code")
    ap.add_argument("--modo", choices=["full", "tutor"])
    ap.add_argument("--tarea", choices=["dipolo", "parche"])
    ap.add_argument("--participante")
    ap.add_argument("--workspace", type=Path, default=WORKSPACE)
    ap.add_argument("--prompts", type=Path, default=PROMPTS)
    ap.add_argument("--mostrar", action="store_true")
    a = ap.parse_args()
    ws = a.workspace.resolve()

    if a.mostrar:
        mcp = ws / ".mcp.json"
        if not mcp.exists():
            sys.exit(f"No hay sesión configurada en {ws}")
        env = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["openems"]["env"]
        head = (ws / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[2] if (ws / "CLAUDE.md").exists() else "(sin CLAUDE.md)"
        print(f"{ws}\n  modo: {env['OPENEMS_MCP_MODE']}\n  participante: {env['OPENEMS_MCP_PARTICIPANT']}\n  {head}")
        return
    if not (a.modo and a.tarea and a.participante):
        ap.error("se requieren --modo, --tarea y --participante (o --mostrar)")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,20}", a.participante):
        sys.exit("Código de participante inválido: usa letras, números, '_' o '-' (sin nombres reales).")
    prompt_file = a.prompts / f"{'ejecutor' if a.modo == 'full' else 'tutor'}_{a.tarea}.md"
    if not prompt_file.exists():
        sys.exit(f"No existe {prompt_file}")

    ws.mkdir(parents=True, exist_ok=True)
    (ws / ".claude").mkdir(exist_ok=True)
    (ws / ".claude" / "settings.json").write_text(json.dumps(settings(), indent=2), encoding="utf-8")
    (ws / ".mcp.json").write_text(json.dumps(mcp_config(a.modo, a.participante, ws), indent=2), encoding="utf-8")
    prompt = prompt_file.read_text(encoding="utf-8")
    (ws / "CLAUDE.md").write_text(
        f"<!-- sesión configurada {datetime.now():%Y-%m-%d %H:%M} | participante {a.participante} | "
        f"modo {a.modo} | tarea {a.tarea} -->\n\n{prompt}", encoding="utf-8")
    print(f"Listo en {ws}: modo={a.modo} tarea={a.tarea} participante={a.participante}\n"
          f"Abre una sesión NUEVA de Claude Code con carpeta de trabajo {ws}.")


if __name__ == "__main__":
    main()
