@echo off
rem Generador de licencias offline - Inventory Master OS
rem Uso: arrastrar o escribir: generador_licencias_offline.bat <codigo> <AAAA-MM-DD>
cd /d "%~dp0"
pythonw generador_licencias_offline.py %1 %2
exit
