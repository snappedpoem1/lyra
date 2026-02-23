@echo off
REM Lyra Oracle CLI (alias)
REM Usage: oracle <command> [options]

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m oracle.cli %*
) else (
    python -m oracle.cli %*
)
