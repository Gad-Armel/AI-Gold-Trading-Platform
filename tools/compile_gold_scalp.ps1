param([string]$MetaEditor = 'C:\Program Files\MetaTrader\MetaEditor64.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath $MetaEditor)) { throw "MetaEditor absent: $MetaEditor" }
$validation = Join-Path $root 'mql5\validation'
New-Item -ItemType Directory -Path $validation -Force | Out-Null
foreach ($name in @('GoldScalpAI', 'GoldScalpSelfTest', 'GoldScalpDashboardPreview', 'GoldScalpNewsFeed', 'GoldScalpNewsBridge')) {
    $relative = if ($name -eq 'GoldScalpNewsFeed') { "mql5\Services\$name.mq5" } elseif ($name -eq 'GoldScalpNewsBridge') { "mql5\Scripts\$name.mq5" } else { "mql5\Experts\GoldScalpAI\$name.mq5" }
    $source = Join-Path $root $relative
    $log = Join-Path $validation "$name.compile.log"
    $started = Get-Date
    $process = Start-Process -FilePath $MetaEditor -ArgumentList ('/compile:"{0}" /log:"{1}"' -f $source,$log) -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(60000)) { throw 'Compilation still running; inspect MetaEditor.' }
    if (!(Test-Path -LiteralPath $log) -or (Get-Item -LiteralPath $log).LastWriteTime -lt $started.AddSeconds(-2)) { throw "Fresh log missing: $log" }
    $summary = Get-Content -LiteralPath $log | Select-String 'Result:' | Select-Object -Last 1
    Write-Output "$name : $summary"
    if (!$summary -or "$summary" -notmatch 'Result: 0 errors, 0 warnings,') { throw "Compilation failed or warned: $log" }
}
