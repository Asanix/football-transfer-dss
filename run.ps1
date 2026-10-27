# Windows: full pipeline, then the dashboard.
#   .\run.ps1                    -> pipeline for Real Madrid + open dashboard
#   .\run.ps1 -Club "Real Sociedad" -NoApp
param([string]$Club = "Real Madrid CF", [switch]$NoApp, [switch]$Rebuild)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
$env:PYTHONPATH = "src"
$extra = @(); if ($Rebuild) { $extra += "--rebuild" }
& $py -m football_dss.pipeline --club $Club @extra
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $NoApp) { & $py -m streamlit run app.py }
