@echo off
REM TrustShield — one-click local launcher (double-click this file, or run `start` in a terminal).
REM Bypasses PowerShell's execution policy for this one script only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
