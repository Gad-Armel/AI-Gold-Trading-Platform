$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$launcher = Join-Path $PSScriptRoot 'launch_gold_demo.py'
if (!(Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Gold demo launcher not found: $launcher" }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -B $launcher --background --yes-demo-risk
    if ($LASTEXITCODE -ne 0) { throw "Gold demo launcher stopped with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
