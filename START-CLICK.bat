@echo off
title Click - starting
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\windows\start-click.ps1"
pause
