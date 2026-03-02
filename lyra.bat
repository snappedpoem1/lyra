@echo off
REM Lyra Oracle CLI
REM Usage: lyra <command> [options]
REM Examples:
REM   lyra status
REM   lyra score --all
REM   lyra pipeline --library "A:\music\Active Music"

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m oracle.cli %*
) else (
    py -3.12 -m oracle.cli %*
)
