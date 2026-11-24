[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv-audit\Scripts\python.exe'
$runner = Join-Path $projectRoot 'run_gold_inverse_bot.py'
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project Python environment is missing.' }
if (Test-Path -LiteralPath 'data/runtime/stop_gold_inverse.flag') {
    throw 'Inverse stop flag is present. Review MT5, then remove only data/runtime/stop_gold_inverse.flag to resume.'
}
$running = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and $_.CommandLine -like "*$projectRoot*" -and
    $_.CommandLine -match '(?:^|[\\\s"''])run_gold_inverse_bot\.py(?:[\s"'']|$)'
})
if ($running.Count) { Write-Host 'Inverse executor already running; no second copy started.'; return }
& $python -u -B $runner --confirm I_ACCEPT_INVERSE_DEMO_RISK
if ($LASTEXITCODE -ne 0) { throw "Inverse executor exited with code $LASTEXITCODE. Review the preceding error." }
