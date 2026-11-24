$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$flag = Join-Path $projectRoot 'data/runtime/stop_gold_inverse.flag'
Set-Content -LiteralPath $flag -Value 'User requested inverse shutdown: close only inverse positions and stop.' -Encoding UTF8
Write-Host 'Inverse stop requested. It closes its own positions only. Verify flat status in data/runtime/gold_inverse_status.json.'
