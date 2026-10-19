# -*- coding: utf-8 -*-
"""
Recoge los datos de una sesión del estudio en una carpeta por participante:

  <destino>/<participante>/<marca de tiempo>/
      transcripciones/*.jsonl   sesiones de Claude Code abiertas en el workspace (copia exacta)
      turnos.csv                las mismas transcripciones en una fila por mensaje, lista para codificar
      mcp_calls.jsonl           llamadas al MCP de ese participante
      proyectos/<carpeta>/      carpetas <participante>_* del workspace, sin la subcarpeta sim/
      manifiesto.json           archivos copiados con su SHA-256

    python recoger_sesion.py --participante P07 --destino "D:\\datos_estudio"

Solo copia transcripciones modificadas desde la recolección anterior en ese workspace.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(os.getenv("OPENEMS_WORKSPACE", r"C:\OPENEMS_MCP_WORK"))


def claude_project_dir(ws: Path) -> Path:
    """Carpeta donde Claude Code guarda las sesiones abiertas en ws (cada carácter no alfanumérico -> '-')."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ws))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def content_rows(rec: dict):
    """Una fila por bloque de contenido de un registro de transcripción."""
    msg = rec.get("message") or {}
    role = msg.get("role") or rec.get("type")
    content = msg.get("content")
    if isinstance(content, str):
        yield role, "texto", content
        return
    for b in content or []:
        t = b.get("type")
        if t == "text":
            yield role, "texto", b.get("text", "")
        elif t == "tool_use":
            yield role, "herramienta", f"{b.get('name')} {json.dumps(b.get('input'), ensure_ascii=False)}"
        elif t == "tool_result":
            c = b.get("content")
            if isinstance(c, list):
                c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
            yield role, "resultado" + (" (error)" if b.get("is_error") else ""), str(c)[:2000]


def main():
    ap = argparse.ArgumentParser(description="Recoge transcripciones, registros y proyectos de una sesión")
    ap.add_argument("--participante", required=True)
    ap.add_argument("--destino", type=Path, required=True)
    ap.add_argument("--workspace", type=Path, default=WORKSPACE)
    ap.add_argument("--todas", action="store_true", help="copiar todas las transcripciones, no solo las nuevas")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,20}", a.participante):
        sys.exit("Código de participante inválido.")
    ws = a.workspace.resolve()
    out = a.destino / a.participante / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True)
    marker = ws / "_logs" / ".ultima_recoleccion"
    since = 0.0 if a.todas or not marker.exists() else float(marker.read_text().strip() or 0)
    copied = []

    # 1. Transcripciones de Claude Code
    tdir = claude_project_dir(ws)
    tout = out / "transcripciones"
    tout.mkdir()
    rows = []
    for f in sorted(tdir.glob("*.jsonl")) if tdir.exists() else []:
        if f.stat().st_mtime <= since:
            continue
        shutil.copy2(f, tout / f.name)
        copied.append(tout / f.name)
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            for role, kind, text in content_rows(rec):
                rows.append([a.participante, f.stem, rec.get("timestamp", ""), role, kind, text])
    with open(out / "turnos.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["participante", "sesion", "hora", "rol", "tipo", "contenido", "codigo"])
        w.writerows(r + [""] for r in rows)
    copied.append(out / "turnos.csv")

    # 2. Registro del MCP filtrado por participante
    calls = []
    for f in sorted((ws / "_logs").glob("mcp_calls_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("participant") == a.participante:
                    calls.append(line)
            except json.JSONDecodeError:
                pass
    (out / "mcp_calls.jsonl").write_text("\n".join(calls) + ("\n" if calls else ""), encoding="utf-8")
    copied.append(out / "mcp_calls.jsonl")

    # 3. Proyectos del participante, sin datos crudos de simulación
    for d in sorted(ws.glob(f"{a.participante}_*")):
        if d.is_dir():
            dst = out / "proyectos" / d.name
            shutil.copytree(d, dst, ignore=shutil.ignore_patterns("sim"))
            copied.extend(p for p in dst.rglob("*") if p.is_file())

    manifest = {
        "participante": a.participante, "workspace": str(ws), "recogido": datetime.now().isoformat(timespec="seconds"),
        "transcripciones_desde": datetime.fromtimestamp(since).isoformat(timespec="seconds") if since else None,
        "archivos": {str(p.relative_to(out)): sha256(p) for p in copied},
    }
    (out / "manifiesto.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(str(datetime.now().timestamp()))
    n_tr = len(list(tout.glob("*.jsonl")))
    print(f"Recogido en {out}\n  transcripciones: {n_tr} ({len(rows)} filas en turnos.csv)\n"
          f"  llamadas MCP: {len(calls)}\n  proyectos: {len(list((out / 'proyectos').glob('*'))) if (out / 'proyectos').exists() else 0}")
    if n_tr == 0:
        print(f"  AVISO: no encontré transcripciones nuevas en {tdir}")


if __name__ == "__main__":
    main()
