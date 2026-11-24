param([string]$MetaEditor = 'C:\Program Files\MetaTrader\MetaEditor64.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath $MetaEditor)) { throw "MetaEditor absent: $MetaEditor" }

$targets = @(
    'mql5\Experts\Exness_XAUUSD_Titan\Exness_XAUUSD_Titan.mq5',
    'mql5\Experts\Exness_XAUUSD_Titan\Exness_XAUUSD_Titan_Test.mq5'
)

foreach ($target in $targets) {
    $source = Join-Path $root $target
    $name = [System.IO.Path]::GetFileNameWithoutExtension($target)
    $log = Join-Path $root "mql5\Experts\Exness_XAUUSD_Titan\$name.compile.log"
    if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log -Force }

    $started = Get-Date
    $process = Start-Process -FilePath $MetaEditor -ArgumentList ('/compile:"{0}" /log:"{1}"' -f $source,$log) -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(60000)) { throw "Compilation still running for ${name}; inspect MetaEditor." }

    Start-Sleep -Milliseconds 500

    if (!(Test-Path -LiteralPath $log)) { throw "Log missing: $log" }
    $content = Get-Content -LiteralPath $log
    $summary = $content | Select-String 'Result:' | Select-Object -Last 1
    Write-Output "=== ${name} ==="
    Write-Output "Summary: $summary"

    if (!$summary -or "$summary" -notmatch 'Result: 0 errors, 0 warnings,') { 
        $content
        throw "Compilation failed or produced warnings for ${name} - $summary" 
    }
}

Write-Output "SUCCESS: All targets compiled cleanly with 0 errors and 0 warnings!"
