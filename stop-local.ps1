$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'scripts\local.py') stop
if ($LASTEXITCODE -ne 0) { throw 'Shutdown failed. See the output.' }
