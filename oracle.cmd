@echo off
setlocal
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Missing venv interpreter: %PY%
  exit /b 1
)
"%PY%" -m oracle.cli %*
exit /b %ERRORLEVEL%
