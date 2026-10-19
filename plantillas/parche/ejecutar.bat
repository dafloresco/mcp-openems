@echo off
rem Ejecuta simulate.py con openEMS. Opciones: --dry, --post-only, --set NOMBRE=VALOR
rem Variables opcionales: CSXCAD_INSTALL_PATH (carpeta de openEMS) y OPENEMS_PYTHON (python con openEMS)
if not defined CSXCAD_INSTALL_PATH set CSXCAD_INSTALL_PATH=C:\openEMS
if not defined OPENEMS_PYTHON set OPENEMS_PYTHON=python
set PYTHONIOENCODING=utf-8
"%OPENEMS_PYTHON%" "%~dp0simulate.py" %*
echo.
echo Resultados en: %~dp0results
pause
