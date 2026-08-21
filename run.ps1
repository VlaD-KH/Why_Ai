# PowerShell Launcher for Why_Ai Self-Evo Sovereign MVP
$env:PYTHONUTF8=1
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "Запуск Self-Evo Sovereign MVP в каталоге Why_Ai..." -ForegroundColor Cyan
python "$ScriptDir\run_mvp.py" @args
