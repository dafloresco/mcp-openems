# -*- coding: utf-8 -*-
"""
Prueba de permisos del modo tutor (nivel servidor), descrita en la sección de implementación del artículo.

1. Inicia el servidor como lo haría el cliente (stdio) en modo "full" y en modo "tutor".
2. Compara las herramientas que cada modo declara al cliente.
3. En modo tutor, intenta llamar a cada herramienta de diseño que solo existe en modo "full"
   y comprueba que el servidor la rechaza sin crear ni modificar archivos del proyecto.
4. Comprueba que la política de permisos que escribe configurar_sesion.py deniega las
   herramientas del cliente que permitirían escribir archivos o ejecutar comandos.

    python prueba_permisos.py            # escribe prueba_permisos.json y termina con código 0 si todo pasa

La prueba del cliente (que Claude Code respete la política) requiere una sesión autenticada y se
hace en el piloto; aquí solo se verifica el contenido de la política.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


def snapshot(ws: Path) -> dict:
    return {str(p.relative_to(ws)): p.stat().st_mtime_ns for p in ws.rglob("*")
            if p.is_file() and "_logs" not in p.parts}


async def tools_of(mode: str, ws: Path, calls=()):
    env = dict(os.environ, OPENEMS_MCP_MODE=mode, OPENEMS_WORKSPACE=str(ws),
               OPENEMS_MCP_PARTICIPANT="PRUEBA", PYTHONIOENCODING="utf-8")
    params = StdioServerParameters(command=sys.executable, args=["-u", str(HERE / "server.py")], env=env)
    results = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            for name in calls:
                try:
                    res = await s.call_tool(name, {})
                    text = " ".join(getattr(c, "text", "") for c in res.content)
                    results.append({"tool": name, "rejected": bool(res.isError), "message": text[:160]})
                except Exception as e:  # noqa: BLE001 - un rechazo por excepción también cuenta como rechazo
                    results.append({"tool": name, "rejected": True, "message": f"{type(e).__name__}: {e}"[:160]})
    return init.protocolVersion, names, results


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        proto, full, _ = await tools_of("full", ws)
        _, tutor, _ = await tools_of("tutor", ws)
        hidden = sorted(set(full) - set(tutor))
        before = snapshot(ws)
        _, _, calls = await tools_of("tutor", ws, calls=hidden)
        unchanged = snapshot(ws) == before

    sys.path.insert(0, str(HERE))
    import configurar_sesion as cs
    pol = cs.settings()["permissions"]
    must_deny = {"Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent"}
    report = {
        "protocolo_mcp": proto,
        "herramientas_full": len(full), "herramientas_tutor": len(tutor),
        "ocultas_en_tutor": hidden,
        "llamadas_prohibidas": len(calls), "rechazadas": sum(c["rejected"] for c in calls),
        "archivos_sin_cambios": unchanged,
        "politica_cliente": {"defaultMode": pol["defaultMode"], "deny_completo": must_deny <= set(pol["deny"]),
                             "allow": pol["allow"]},
        "detalle": calls,
    }
    ok = (report["rechazadas"] == len(calls) and unchanged and report["politica_cliente"]["deny_completo"]
          and not set(tutor) - set(full))
    report["resultado"] = "PASA" if ok else "FALLA"
    (HERE / "prueba_permisos.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "detalle"}, indent=2, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
