@echo off
cd /d "%~dp0"
python snap_saver.py
if errorlevel 1 pause
