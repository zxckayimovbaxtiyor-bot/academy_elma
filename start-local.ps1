param([switch]$Demo)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment is missing. Follow LOCAL-RUN.md first.'
}
$env:PYTHONUTF8 = '1'
$arguments = @((Join-Path $PSScriptRoot 'scripts\local.py'), 'start')
if ($Demo) { $arguments += '--demo' }
& $pythonPath @arguments
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. See the output and .local logs.' }
