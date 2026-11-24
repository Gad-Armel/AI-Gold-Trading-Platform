param(
    [string]$DataDirectory = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\F762D69EEEA9B4430D7F17C82167C844'),
    [string]$Terminal = 'C:\Program Files\MetaTrader 5\terminal64.exe',
    [string]$Symbol = 'XAUUSD',
    [switch]$DemoOrders,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($Symbol -notmatch '^XAUUSD[A-Za-z0-9_.-]*$') { throw 'Use the exact XAUUSD symbol name shown by your broker.' }
if (!(Test-Path -LiteralPath $Terminal -PathType Leaf)) { throw "MT5 executable not found: $Terminal" }
$mql = Join-Path (Resolve-Path -LiteralPath $DataDirectory).Path 'MQL5'
if (!(Test-Path -LiteralPath $mql -PathType Container)) { throw 'DataDirectory must be the MT5 File > Open Data Folder location.' }
$compiled = Join-Path $root 'mql5\Experts\GoldScalpAI\GoldScalpAI.ex5'
$installed = Join-Path $mql 'Experts\GoldScalpAI\GoldScalpAI.ex5'
if (!(Test-Path -LiteralPath $installed) -or !(Test-Path -LiteralPath $compiled)) { throw 'Install the compiled EA first using tools\install_gold_scalp.ps1.' }
if ((Get-FileHash -LiteralPath $compiled).Hash -ne (Get-FileHash -LiteralPath $installed).Hash) { throw 'The installed EA is outdated. Run tools\install_gold_scalp.ps1 first.' }
$newsCompiled = Join-Path $root 'mql5\Scripts\GoldScalpNewsBridge.ex5'
$newsInstalled = Join-Path $mql 'Scripts\GoldScalpNewsBridge.ex5'
if (!(Test-Path -LiteralPath $newsInstalled) -or !(Test-Path -LiteralPath $newsCompiled)) { throw 'Install the native news bridge using tools\install_gold_scalp.ps1 first.' }
if ((Get-FileHash -LiteralPath $newsCompiled).Hash -ne (Get-FileHash -LiteralPath $newsInstalled).Hash) { throw 'Installed news bridge is outdated; reinstall the current build.' }
if (!$PrepareOnly) {
    # MT5 ignores startup configuration when reusing an already running instance.
    # Do not terminate the user's terminal or interrupt other strategies here.
    $terminalPath = (Resolve-Path -LiteralPath $Terminal).Path
    $running = @(Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object { !$_.Path -or $_.Path -eq $terminalPath })
    if ($running.Count) { throw 'Close MetaTrader 5 using File > Exit, then run this command again. Leave the browser dashboard open. Startup attachment requires a fresh terminal launch.' }
}
$runtime = Join-Path $root 'data\runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$presets = Join-Path $mql 'Presets'
New-Item -ItemType Directory -Path $presets -Force | Out-Null
$tradeValue = if ($DemoOrders) { 'true' } else { 'false' }
$allowTrade = if ($DemoOrders) { 1 } else { 0 }
$preset = Join-Path $presets 'GoldScalpAI-launch.set'
@"
EnableDemoOrders=$tradeValue
MaxPositions=3
RollingLossLimitUSD=5.0
DailyEquityLossPercent=3.0
LossStreakLimit=3
LossCooldownMinutes=1
ExpertScalpMode=true
BlockAsiaSession=false
Advisor1Mode=0
UseBrokerTakeProfit=false
MaxSpreadPrice=0.60
SpreadAverageMultiplier=1.8
MaximumSpreadATR=0.50
MaximumCostFraction=0.45
MinimumRelativeVolume=0.35
StopATR=0.65
ConfirmationSeconds=1
MinimumEntrySeconds=1
MaxEntriesPerHour=60
FrequentEntryMode=true
MinimumScalpScore=50
ProfitGivebackFraction=0.333333
MinimumProfitArmUSD=0.35
AdaptiveSessions=true
UseRapidRotation=true
UseRapidContinuation=true
UseTrendContinuation=true
RapidRearmMilliseconds=250
UseImpulseAcceleration=true
UseConfirmationGrace=true
UseCounterflowGuard=true
AllowBrowserControls=true
ShowDashboard=false
BrowserDashboardOnly=true
ExportWebDashboard=true
"@ | Set-Content -LiteralPath $preset -Encoding Unicode
$config = Join-Path $runtime 'gold_scalp_startup.ini'
@"
[Experts]
Enabled=1
AllowLiveTrading=$allowTrade
AllowDllImport=0
[StartUp]
Expert=GoldScalpAI\GoldScalpAI
ExpertParameters=GoldScalpAI-launch.set
Script=GoldScalpNewsBridge
Symbol=$Symbol
Period=M1
ShutdownTerminal=0
"@ | Set-Content -LiteralPath $config -Encoding Unicode
if ($PrepareOnly) { Write-Output "Prepared startup config: $config. MT5 was not launched."; return }
$started = Get-Date
# This is the user's interactive MT5 window, so keep it visible.
$process = Start-Process -FilePath $Terminal -ArgumentList ('/config:"{0}"' -f $config) -PassThru
Write-Output "MT5 launched (PID $($process.Id)). Waiting up to 60 seconds for the EA heartbeat..."
Write-Output "EnableDemoOrders=$tradeValue; volume/risk limits remain those of the EA."
try {
    & (Join-Path $PSScriptRoot 'open_gold_unified_dashboard.ps1')
} catch {
    Write-Warning "MT5 is running, but the unified dashboard could not open: $_"
    Write-Warning 'Retry with: powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\open_gold_unified_dashboard.ps1'
}
$feedDirectory = Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common\Files\GoldScalp'
$deadline = $started.AddSeconds(60)
do {
    foreach ($file in @(Get-ChildItem -LiteralPath $feedDirectory -Filter 'dashboard_*.json' -ErrorAction SilentlyContinue)) {
        if ($file.LastWriteTime -lt $started -or $file.LastWriteTime -lt (Get-Date).AddSeconds(-5)) { continue }
        try { $feed = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
        if ($feed.schema -eq 1 -and $feed.symbol -eq $Symbol -and !$feed.stopped) {
            Write-Output "EA heartbeat received: $($feed.mode) | $($feed.status)"
            Write-Output 'The unified dashboard at http://127.0.0.1:8777 will update automatically.'
            Write-Output 'Native news bridge starts with MT5. The unified dashboard publishes Advisor 1 reports.'
            return
        }
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
Write-Warning 'MT5 opened, but no fresh EA heartbeat arrived. Check MT5 > Toolbox (Ctrl+T) > Experts.'
$logDirectory = Join-Path $mql 'Logs'
$log = Get-ChildItem -LiteralPath $logDirectory -Filter '*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($log) { Get-Content -LiteralPath $log.FullName -Tail 80 | Select-String 'GoldScalp|initialization|failed|lock|DISABLED|required' | Select-Object -Last 12 | ForEach-Object { Write-Output $_.Line } }
exit 1
