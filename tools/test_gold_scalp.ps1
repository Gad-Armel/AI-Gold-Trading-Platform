param(
    [string]$TerminalDirectory = 'C:\Program Files\MetaTrader',
    [switch]$RealTicks,
    [string]$FromDate = '2026.09.14',
    [string]$ToDate = '2026.09.16',
    [string]$BrokerDataDirectory = '',
    [string]$BrokerServer = 'Coinexx-Demo',
    [long]$DemoLogin = 0
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ($RealTicks -and $DemoLogin -le 0) { throw 'Historical tests require a connected demo account. Use MT5 Strategy Tester in your normal demo terminal, or connect this isolated terminal and specify DemoLogin.' }
$sources = Join-Path $root 'mql5\Experts\GoldScalpAI'
foreach ($name in @('GoldScalpAI','GoldScalpSelfTest')) {
    $binary = Join-Path $sources "$name.ex5"
    $latestSource = @(Get-Item -LiteralPath (Join-Path $sources "$name.mq5")) + @(Get-ChildItem -LiteralPath $sources -Filter '*.mqh') | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!(Test-Path -LiteralPath $binary) -or (Get-Item -LiteralPath $binary).LastWriteTime -lt $latestSource.LastWriteTime) { throw "Missing/stale binary $name; compile successfully first." }
}
$stage = Join-Path $root '.mt5-validation'
$expertDir = Join-Path $stage 'MQL5\Experts\GoldScalpAI'
New-Item -ItemType Directory -Path $expertDir -Force | Out-Null
$testerFiles = Join-Path $stage 'MQL5\Files'
New-Item -ItemType Directory -Path $testerFiles -Force | Out-Null
$tickFixture = Join-Path $root 'data\research\scalper_expert3\scalp_ticks.csv'
if (Test-Path -LiteralPath $tickFixture) {
    Copy-Item -LiteralPath $tickFixture -Destination (Join-Path $testerFiles 'scalp_ticks.csv') -Force
} else {
    # Declared tester_file must exist even when the optional broker replay is absent.
    [System.IO.File]::WriteAllText((Join-Path $testerFiles 'scalp_ticks.csv'), '')
}
foreach ($program in @('terminal64.exe', 'metatester64.exe')) {
    # Reuse the isolated installation; replacing a loaded executable races MT5 shutdown/update.
    if (!(Test-Path -LiteralPath (Join-Path $stage $program))) {
        Copy-Item -LiteralPath (Join-Path $TerminalDirectory $program) -Destination $stage
    }
}
Copy-Item -Path (Join-Path $root 'mql5\Experts\GoldScalpAI\*.ex5') -Destination $expertDir -Force
if ($RealTicks -and !$BrokerDataDirectory) { throw 'RealTicks requires BrokerDataDirectory containing cached broker bases. No account credentials are copied.' }
if ($BrokerDataDirectory) {
    foreach ($kind in @('symbols', 'history', 'ticks')) {
        $from = Join-Path $BrokerDataDirectory "bases\$BrokerServer\$kind"
        $to = Join-Path $stage "bases\$BrokerServer\$kind"
        New-Item -ItemType Directory -Path $to -Force | Out-Null
        if ($kind -eq 'symbols') {
            Get-ChildItem -LiteralPath $from -File | Copy-Item -Destination $to -Force
        } elseif (Test-Path -LiteralPath (Join-Path $from 'XAUUSD')) {
            Copy-Item -LiteralPath (Join-Path $from 'XAUUSD') -Destination $to -Recurse -Force
        }
    }
    $configDir = Join-Path $stage 'Config'
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    $servers = Join-Path $BrokerDataDirectory 'config\servers.dat'
    if (Test-Path -LiteralPath $servers) { Copy-Item -LiteralPath $servers -Destination $configDir -Force }
}
$expert = if ($RealTicks) { 'GoldScalpAI' } else { 'GoldScalpSelfTest' }
$model = if ($RealTicks) { 4 } else { 3 }
$config = Join-Path $stage 'validation.ini'
$report = Join-Path $root "mql5\validation\$expert-report.html"
@"
[Common]
Server=$BrokerServer
Login=$DemoLogin
[Experts]
Enabled=0
AllowLiveTrading=0
AllowDllImport=0
[Tester]
Expert=GoldScalpAI\$expert.ex5
Symbol=XAUUSD
Period=M1
Model=$model
ExecutionMode=150
Optimization=0
FromDate=$FromDate
ToDate=$ToDate
Deposit=100
Currency=USD
Leverage=100
UseLocal=1
UseRemote=0
UseCloud=0
Visual=0
Report=$report
ReplaceReport=1
ShutdownTerminal=1
"@ | Set-Content -LiteralPath $config -Encoding Unicode
$process = Start-Process -FilePath (Join-Path $stage 'terminal64.exe') -ArgumentList ('/portable /skipupdate /config:"{0}"' -f $config) -WorkingDirectory $stage -WindowStyle Hidden -PassThru
Write-Output "Isolated tester PID=$($process.Id); config=$config; logs=$stage\Tester; report=$report"
Write-Output 'This launch alone is not proof of a completed test. Verify GOLD_SELF_TEST or VALIDATION_SUMMARY in the agent journal.'
