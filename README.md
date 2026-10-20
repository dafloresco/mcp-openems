# mcp-openems

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23487839.svg)](https://doi.org/10.5281/zenodo.23487839)

Servidor [MCP](https://modelcontextprotocol.io) (Model Context Protocol) que conecta un agente de inteligencia artificial con el simulador electromagnético libre [openEMS](https://www.openems.de) (FDTD). Lo hace en dos modos de uso pensados para la docencia de antenas:

- **Ejecutor:** el agente diseña, simula y ajusta la antena.
- **Tutor:** el estudiante escribe el diseño y el agente solo simula, revisa y orienta. Las herramientas que crean o modifican el modelo se retiran desde el servidor.

Es el software que acompaña al artículo *¿Ejecutor o tutor? Agentes de IA conectados a simuladores en la enseñanza de antenas* (en evaluación). Para citar el software:

> Flores Córdova, D. A. (2026). *mcp-openems: servidor MCP para openEMS con modos ejecutor y tutor* (Versión 0.3.0) [Software]. Zenodo. https://doi.org/10.5281/zenodo.23487839

El DOI anterior es el DOI de concepto: siempre resuelve a la última versión. Cada versión tiene además su propio DOI en Zenodo. La versión que describe el artículo es la 0.3.0.

Los metadatos completos están en [`CITATION.cff`](CITATION.cff).

> *English summary:* an MCP server that lets an AI agent drive the openEMS FDTD simulator in two teaching modes. In **executor** mode the agent designs the antenna. In **tutor** mode the student designs it and the agent may only run, check and explain, because design tools are removed at the server level. It includes student templates, agent prompts, session-logging tools and the scripts that reproduce the article's verification tables and a permission test of tutor mode.

## Contenido

| Ruta | Qué es |
|---|---|
| `server.py` | Servidor MCP (FastMCP): 42 herramientas en modo ejecutor y 17 en modo tutor |
| `openems_bridge.py` | Lógica de proyectos, simulaciones en segundo plano, resultados y revisión del diseño |
| `openems_scriptgen.py` | Genera un `simulate.py` legible y autocontenido a partir del modelo |
| `sweep_driver.py` | Barridos paramétricos |
| `configurar_sesion.py` | Prepara una sesión del estudio en Claude Code: modo, participante y permisos |
| `recoger_sesion.py` | Reúne transcripciones, registro MCP y proyectos de un participante, con SHA-256 |
| `selftest.py` | Prueba de extremo a extremo del servidor |
| `prueba_permisos.py` | Prueba de permisos del modo tutor: herramientas declaradas, llamadas prohibidas y política del cliente |
| `requirements.txt`, `requirements-lock.txt` | Dependencias mínimas y entorno exacto del artículo |
| `ENTORNO.md` | Equipo, sistema operativo y versiones usados en el artículo |
| `plantillas/` | Plantillas del estudiante para el modo tutor (dipolo y parche) |
| `prompts/` | Instrucciones del agente por modo y por tarea |
| `simulaciones/` | Scripts de la prueba técnica: casos de referencia, estudios de control, extrapolación de convergencia y contraste con CST |
| `busqueda/` | Búsqueda bibliográfica documentada: ecuaciones, scripts de descarga y deduplicación, y registro completo del cribado |
| `protocolo/` | Simulación de potencia del modelo mixto del estudio propuesto |

## Requisitos

- Windows 10 u 11. Probado en Windows 11 con openEMS 0.37.0 y Python 3.14. El servidor tiene una ruta POSIX, pero no se probó en Linux ni en macOS.
- [openEMS 0.37](https://github.com/thliebig/openEMS-Project/releases) para Windows, descomprimido por ejemplo en `C:\openEMS`.
- Python 3.13 o 3.14, porque las ruedas de openEMS 0.37 solo existen para esas versiones.
- Un cliente MCP, por ejemplo Claude Desktop o Claude Code.

## Instalación

```bat
cd mcp-openems
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install --no-index --find-links C:\openEMS\python openEMS
set CSXCAD_INSTALL_PATH=C:\openEMS
.venv\Scripts\python selftest.py --quick
```

Para el entorno exacto del artículo, usa `requirements-lock.txt` en lugar de `requirements.txt` (ver [`ENTORNO.md`](ENTORNO.md)). `mcp` se fija en `<2` porque la versión 2.x renombró FastMCP. Si se prefiere [uv](https://docs.astral.sh/uv/), los comandos equivalentes son `uv venv --python 3.14 .venv` y `uv pip install --python .venv\Scripts\python.exe ...`.

### Registro en el cliente MCP

Ejemplo de entrada en `claude_desktop_config.json` o en un `.mcp.json` de proyecto (ajusta las rutas):

```json
{
  "mcpServers": {
    "openems": {
      "command": "C:\\ruta\\mcp-openems\\.venv\\Scripts\\python.exe",
      "args": ["-u", "C:\\ruta\\mcp-openems\\server.py"],
      "env": {
        "CSXCAD_INSTALL_PATH": "C:\\openEMS",
        "OPENEMS_WORKSPACE": "C:\\OPENEMS_MCP_WORK",
        "OPENEMS_MCP_MODE": "full",
        "OPENEMS_MCP_PARTICIPANT": ""
      }
    }
  }
}
```

| Variable | Valor por defecto | Uso |
|---|---|---|
| `OPENEMS_WORKSPACE` | `C:\OPENEMS_MCP_WORK` | Carpeta de proyectos. El servidor no lee ni escribe fuera de ella |
| `CSXCAD_INSTALL_PATH` | `C:\openEMS-0.37.0` | Carpeta con `openEMS.exe` y `CSXCAD.dll` |
| `OPENEMS_MCP_MODE` | `full` | `full` (ejecutor) o `tutor` |
| `OPENEMS_MCP_PARTICIPANT` | vacío | Código seudónimo que se guarda en el registro de llamadas |

## Cómo funciona

- **Cada proyecto es una carpeta** con un modelo declarativo (`model.json`) y un `simulate.py` generado a partir de él. El script es legible: los parámetros son variables y la geometría son expresiones como `-L/2`. Se ejecuta sin el agente (`python simulate.py`, con las opciones `--dry`, `--post-only`, `--set L=29.5`).
- **Las simulaciones corren en un subproceso**, de modo que el servidor nunca importa openEMS.
- **Post-proceso:** S11, impedancia de entrada, ancho de banda a −10 dB, directividad, eficiencia de radiación y ganancia realizada. Se guardan en CSV, PNG, Touchstone y `summary.json`.
- **Modo tutor:** las 25 herramientas que crean o modifican el modelo no se registran. Quedan las de abrir proyectos, ejecutar el script del estudiante, revisar la malla y el diseño, leer resultados y generar el reporte.
- **Registro:** cada llamada se guarda en `OPENEMS_WORKSPACE\_logs\mcp_calls_AAAAMMDD.jsonl` con la hora, el participante, el modo, la herramienta, los argumentos y un extracto del resultado.
- **Contornos PEC o PMC** sin margen de aire en esa cara. Así se modela un plano de tierra infinito, por ejemplo con `BC[4] = 'PEC'` para un monopolo.

## Uso en un estudio con estudiantes

1. **Configurar la sesión.** `configurar_sesion.py --modo tutor --tarea dipolo --participante P07` escribe en el workspace el `CLAUDE.md` con el prompt del modo, el `.mcp.json` con el modo y el participante, y permisos `dontAsk`: solo las herramientas `oems_*` y la lectura de archivos.
   - Abre una sesión nueva de Claude Code en el workspace y acepta una vez el diálogo de confianza de la carpeta.
   - No registres `openems` también en `claude_desktop_config.json`.
2. **Recoger los datos.** Al terminar, `recoger_sesion.py --participante P07 --destino D:\datos` copia la transcripción, el registro y los proyectos, y genera `turnos.csv` para codificar.
3. **Plantillas.** Las de `plantillas/` dan al estudiante del modo tutor la misma estructura de script que genera el servidor en el modo ejecutor.

## Reproducir la verificación del artículo

```bat
cd simulaciones
..\.venv\Scripts\python reproducir_tabla2.py      &REM siete casos de referencia
..\.venv\Scripts\python estudios_control.py       &REM convergencia, repetición, contornos y pérdidas
..\.venv\Scripts\python extrapolacion.py         &REM extrapolación de Richardson de las series de convergencia
cd ..
.venv\Scripts\python prueba_permisos.py            &REM prueba de permisos del modo tutor
```

Ver [`simulaciones/README.md`](simulaciones/README.md) para los casos, los tiempos y las tolerancias, [`busqueda/README.md`](busqueda/README.md) para la búsqueda bibliográfica y [`protocolo/README.md`](protocolo/README.md) para la simulación de potencia.

## Qué no se publica y por qué

- **Soluciones de las tareas del estudio.** Publicarlas invalidaría las tareas para los participantes. Se compartirán con otros docentes a solicitud.
- **Transcripciones y registros de participantes.** Contienen datos personales; solo se publicarán datos agregados y registros codificados, según el plan de gobernanza de datos del estudio.
- **Resúmenes de los registros bibliográficos.** Están protegidos por derechos de autor de sus editores; `busqueda/` publica sus metadatos y las decisiones del cribado.
- **Modelo de CST Studio Suite** usado como contraste. Requiere una licencia comercial; sus resultados están en `simulaciones/contraste_cst.csv`.

## Licencia y créditos

Código bajo licencia [MIT](LICENSE). openEMS y CSXCAD son proyectos independientes con su propia licencia (GPLv3); este repositorio no los incluye ni los redistribuye.

El software se desarrolló con asistencia de Claude (Anthropic). El autor lo revisó y verificó.
