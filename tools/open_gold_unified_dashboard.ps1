[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot 'run_gold_unified_dashboard.py'
$url = 'http://127.0.0.1:8777/'
$healthUrl = $url + 'health'
$expected = 'aurum-gold-unified'
$pythonPath = (Get-Command python -ErrorAction Stop).Source
if (!(Test-Path -LiteralPath $runner -PathType Leaf)) { throw "Unified dashboard runner not found: $runner" }

function Test-UnifiedDashboard {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
        if ($health.dashboard -and $health.dashboard -ne $expected) {
            throw 'Port 8777 belongs to a different dashboard. No second server was started.'
        }
        return $health.dashboard -eq $expected
    } catch {
        if ($_.Exception.Message -like '*belongs to a different dashboard*') { throw }
        return $false
    }
}

$ready = Test-UnifiedDashboard
if (!$ready) {
    $runtime = Join-Path $projectRoot 'data\runtime'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $process = Start-Process -FilePath $pythonPath `
        -ArgumentList ('-B "{0}" --no-browser' -f $runner) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime 'unified-dashboard.stdout.log') `
        -RedirectStandardError (Join-Path $runtime 'unified-dashboard.stderr.log') -PassThru
    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $ready = Test-UnifiedDashboard
        if ($ready) { break }
        if ($process.HasExited) { throw 'Unified dashboard exited during startup; see data/runtime/unified-dashboard.stderr.log.' }
    } while ((Get-Date) -lt $deadline)
}
if (!$ready) { throw 'Unified dashboard did not respond at http://127.0.0.1:8777/ within 15 seconds.' }
if (!$NoBrowser) { Start-Process $url }
Write-Output "Unified Gold Demo Desk ready: $url"
