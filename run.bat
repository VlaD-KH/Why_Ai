@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
echo ===================================================
echo  Starting Self-Evo Sovereign MVP in Why_Ai...
echo ===================================================
python "%~dp0run_mvp.py" %*
pause
