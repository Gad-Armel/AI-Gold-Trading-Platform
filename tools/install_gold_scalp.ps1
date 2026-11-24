param([Parameter(Mandatory=$true)][string]$DataDirectory)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$mql = Join-Path (Resolve-Path -LiteralPath $DataDirectory).Path 'MQL5'
if (!(Test-Path -LiteralPath $mql -PathType Container)) { throw 'Choose the MT5 data folder shown by File > Open Data Folder.' }
$source = Join-Path $root 'mql5\Experts\GoldScalpAI'
$latestHeader = Get-ChildItem -LiteralPath $source -Filter '*.mqh' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
foreach ($name in @('GoldScalpAI','GoldScalpSelfTest','GoldScalpDashboardPreview')) {
    $binary = Join-Path $source "$name.ex5"
    if (!(Test-Path -LiteralPath $binary) -or (Get-Item -LiteralPath $binary).LastWriteTime -lt $latestHeader.LastWriteTime -or (Get-Item -LiteralPath $binary).LastWriteTime -lt (Get-Item -LiteralPath (Join-Path $source "$name.mq5")).LastWriteTime) { throw "Compile first: $name is missing or stale." }
}
$service = Join-Path $root 'mql5\Services\GoldScalpNewsFeed.ex5'
if (!(Test-Path -LiteralPath $service) -or (Get-Item -LiteralPath $service).LastWriteTime -lt (Get-Item -LiteralPath (Join-Path $root 'mql5\Services\GoldScalpNewsFeed.mq5')).LastWriteTime) { throw 'Compile the native news service first.' }
$destination = Join-Path $mql 'Experts\GoldScalpAI'
$newsBridge = Join-Path $root 'mql5\Scripts\GoldScalpNewsBridge.ex5'
if (!(Test-Path -LiteralPath $newsBridge)) { throw 'Compile GoldScalpNewsBridge first.' }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Get-ChildItem -LiteralPath $source -File | Where-Object Extension -in @('.mq5','.mqh','.ex5') | Copy-Item -Destination $destination -Force
$services = Join-Path $mql 'Services'
New-Item -ItemType Directory -Path $services -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'mql5\Services') -Filter 'GoldScalpNewsFeed.*' | Copy-Item -Destination $services -Force
Copy-Item -LiteralPath (Join-Path $root 'mql5\Services\GoldScalpNewsPublisher.mqh') -Destination $services -Force
$scripts = Join-Path $mql 'Scripts'
New-Item -ItemType Directory -Path $scripts -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'mql5\Scripts') -Filter 'GoldScalpNewsBridge.*' | Copy-Item -Destination $scripts -Force
Write-Output "Installation complete: $mql"
Write-Output 'NEXT: Close MT5 normally, then launch the EA and native news worker:'
Write-Output 'powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_scalp_mt5.ps1 -DemoOrders'
Write-Output 'Omit -DemoOrders for observation only. The chart dashboard is hidden by default.'
Write-Output 'Open the single unified browser dashboard and Advisor 1 report bridge with:'
Write-Output 'powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\open_gold_unified_dashboard.ps1'
Write-Output 'Installation alone does not attach an EA or change trading permissions.'
