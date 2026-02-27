@echo off
title Lyra Oracle — Boot
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" boot_oracle.py
) else (
    py -3.12 boot_oracle.py
)
