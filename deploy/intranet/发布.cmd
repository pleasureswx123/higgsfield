@echo off
setlocal
set "PYTHONUTF8=1"
set "PY=%~dp0..\..\ruoyi-fastapi-backend\.venv\Scripts\python.exe"
if exist "%PY%" goto run
echo Missing project Python environment: "%PY%"
exit /b 1
:run
"%PY%" -u "%~dp0release_windows.py" publish %*
set "code=%errorlevel%"
if "%~1"=="" pause
exit /b %code%
