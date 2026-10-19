@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-desktop.ps1"
if errorlevel 1 (
    echo BUILD FAILED. Read the error above.
) else (
    echo SUCCESS. The EXE is in the dist folder.
)
pause
